# Interface Contract — Core (FSM)

spec-version: 1.0

## Module: fsm

Function: add_new_state
Input:
  - state_name
Output: State
Error:
  - Raise InvalidStateError nếu state_name không nằm trong ALLOWED_STATES
  - Raise DuplicateStateError nếu state_name đã tồn tại

Function: get_current_state
Input: None
Output: State | None

Function: transition_to
Input:
  - target_state
Output: State
Error:
  - Raise InvalidStateError nếu target_state không nằm trong ALLOWED_STATES
  - Raise InvalidTransitionError nếu target_state chưa đăng ký

Function: reset_states
Input: None
Output: None
Notes:
  - Xóa toàn bộ registry (_states.clear())
  - Reset current_state về None
  - Sau reset, transition_to sẽ raise InvalidTransitionError
