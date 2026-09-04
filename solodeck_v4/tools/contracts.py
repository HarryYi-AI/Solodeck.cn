from __future__ import annotations

import signal
import threading
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from time import perf_counter
from typing import Any, Callable, Iterator
from uuid import uuid4


ToolFn = Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]]


class ToolTimeoutError(TimeoutError):
    pass


@dataclass(frozen=True)
class ToolContract:
    name: str
    fn: ToolFn
    description: str
    permission: str
    timeout_seconds: float
    cost_hint: float
    required_state: tuple[str, ...] = ()
    required_args: tuple[str, ...] = ()
    required_output: tuple[str, ...] = ("ok",)
    retryable_errors: tuple[str, ...] = ("timeout", "execution_error")
    side_effects: tuple[str, ...] = ()
    version: str = "1.0.0"

    def public_schema(self) -> dict[str, Any]:
        value = asdict(self)
        value.pop("fn", None)
        return value


def dispatch_tool(contract: ToolContract, state: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
    call_id = f"tool_{uuid4().hex[:16]}"
    from solodeck_v4.observability import tool_observation, update_observation

    with tool_observation(contract.name, call_id, contract.permission, args) as observation:
        result, audit = _dispatch_tool(contract, state, args, call_id)
        update_observation(
            observation,
            output={
                "ok": bool(result.get("ok")),
                "latency_ms": audit["latency_ms"],
                "error_type": audit["error_type"],
            },
            metadata={
                "status": audit["status"],
                "cost": audit["cost"],
                "contract_version": audit["contract_version"],
            },
        )
    state.setdefault("tool_audit", []).append(audit)
    return result


def _dispatch_tool(
    contract: ToolContract,
    state: dict[str, Any],
    args: dict[str, Any],
    call_id: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    started = perf_counter()
    status = "ok"
    error_type = None
    error_message = None
    result: dict[str, Any]
    try:
        _check_permission(contract, state)
        _check_inputs(contract, state, args)
        with _deadline(contract.timeout_seconds):
            result = contract.fn(state, args)
        _check_output(contract, result)
    except PermissionError as exc:
        status, error_type, error_message = "error", "permission_denied", str(exc)
        result = _error_result(contract, error_type, error_message, retryable=False)
    except (KeyError, TypeError, ValueError) as exc:
        status, error_type, error_message = "error", "invalid_input", str(exc)
        result = _error_result(contract, error_type, error_message, retryable=False)
    except ToolTimeoutError as exc:
        status, error_type, error_message = "error", "timeout", str(exc)
        result = _error_result(contract, error_type, error_message, retryable=True)
    except Exception as exc:
        status, error_type = "error", "execution_error"
        error_message = f"{type(exc).__name__}: {exc}"
        result = _error_result(contract, error_type, error_message, retryable=True)
    latency_ms = round((perf_counter() - started) * 1000, 3)
    if latency_ms > contract.timeout_seconds * 1000 and status == "ok":
        status, error_type = "warning", "soft_timeout"
        result.setdefault("warnings", []).append("工具执行超过软超时预算")
    result.setdefault("tool", contract.name)
    result.setdefault("call_id", call_id)
    result.setdefault("latency_ms", latency_ms)
    result.setdefault("contract_version", contract.version)
    audit = {
        "call_id": call_id,
        "tool": contract.name,
        "permission": contract.permission,
        "status": status,
        "error_type": error_type,
        "error_message": _safe_error(error_message),
        "latency_ms": latency_ms,
        "cost": float(result.get("cost", contract.cost_hint)),
        "contract_version": contract.version,
        "arg_keys": sorted(args),
        "side_effects": list(contract.side_effects),
    }
    return result, audit


def _check_permission(contract: ToolContract, state: dict[str, Any]) -> None:
    permissions = state.get("permissions")
    if permissions is None:
        return
    if contract.permission not in set(permissions):
        raise PermissionError(f"tool {contract.name} requires permission {contract.permission}")


def _check_inputs(contract: ToolContract, state: dict[str, Any], args: dict[str, Any]) -> None:
    missing_state = [name for name in contract.required_state if state.get(name) is None]
    missing_args = [name for name in contract.required_args if args.get(name) is None]
    if missing_state or missing_args:
        raise ValueError(f"missing state={missing_state}, args={missing_args}")


def _check_output(contract: ToolContract, result: Any) -> None:
    if not isinstance(result, dict):
        raise TypeError("tool output must be a dict")
    missing = [name for name in contract.required_output if name not in result]
    if missing:
        raise ValueError(f"tool output missing fields: {missing}")


def _error_result(contract: ToolContract, error_type: str, message: str, *, retryable: bool) -> dict[str, Any]:
    return {
        "ok": False,
        "error": {"type": error_type, "message": _safe_error(message), "retryable": retryable},
        "cost": 0.0,
        "tool": contract.name,
    }


def _safe_error(value: str | None) -> str | None:
    if value is None:
        return None
    return value[:300]


@contextmanager
def _deadline(seconds: float) -> Iterator[None]:
    """Hard timeout on the main Unix thread; soft budget elsewhere."""
    if seconds <= 0 or threading.current_thread() is not threading.main_thread() or not hasattr(signal, "setitimer"):
        yield
        return

    def handler(signum: int, frame: Any) -> None:
        raise ToolTimeoutError(f"tool exceeded {seconds:.1f}s timeout")

    previous = signal.getsignal(signal.SIGALRM)
    signal.signal(signal.SIGALRM, handler)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)
