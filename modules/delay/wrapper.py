"""Behavior wrapper — decorates a task function with delay injection.

Wraps ``task_fn`` so that behavioral delay is injected at safe points
*without* altering execution logic, scaling, or orchestration flow.
"""
import time

from modules.delay.persona import PersonaProfile
from modules.delay.state import BehaviorStateMachine
from modules.delay.engine import DelayEngine
from modules.delay.temporal import TemporalModel


def wrap(task_fn, persona: PersonaProfile):
    """Return a wrapped version of *task_fn* with behavioral delay.

    The wrapped function preserves the original signature and return
    value.  Delay is injected *before* each call only when the
    behavior state machine considers it safe (SAFE ZONE).

    Parameters
    ----------
    task_fn : callable
        The original worker task function ``(worker_id) -> result``.
    persona : PersonaProfile
        Persona providing delay attributes for the worker.

    Returns
    -------
    callable
        Wrapped function with the same signature as *task_fn*.
    """
    state_machine = BehaviorStateMachine()
    engine = DelayEngine(persona, state_machine)
    temporal = TemporalModel(persona)

    def _wrapped(worker_id):
        # Transition to FILLING_FORM for the upcoming UI interaction
        state_machine.transition("FILLING_FORM")

        # Calculate and apply delay only when permitted
        if engine.is_delay_permitted():
            delay = engine.calculate_delay("typing")
            delay = temporal.apply_temporal_modifier(delay, "typing")
            delay = temporal.apply_micro_variation(delay)
            if delay > 0:
                time.sleep(delay)

        # Execute the original task — outcome unchanged
        result = task_fn(worker_id)

        # Reset for next step
        engine.reset_step_accumulator()
        state_machine.reset()

        return result

    return _wrapped
