# FSM Specification

spec-version: 1.0

## ALLOWED_STATES (Tập đóng)
- ui_lock
- success
- vbv_3ds
- declined

## State Semantics
| State     | Mô tả                                           | Terminal? |
|-----------|--------------------------------------------------|-----------|
| ui_lock   | Form đơ, cần focus-shift retry                   | No        |
| success   | Đơn hàng thành công, URL → /confirmation         | Yes       |
| vbv_3ds   | Iframe 3D-Secure xuất hiện                       | No        |
| declined  | Giao dịch bị từ chối, cần swap thẻ              | No        |

## Transitions (Runtime — Phase 3+)
- ui_lock  → success | vbv_3ds | declined
- vbv_3ds  → declined | success
- declined → declined (swap thẻ) | [end cycle]

## Registry Rules
- Mỗi state chỉ đăng ký 1 lần (singleton per name)
- Thread-safe qua Lock
- ALLOWED_STATES là tập đóng — không mở rộng runtime

## Error Contract
| Scenario                          | Exception              |
|-----------------------------------|------------------------|
| state_name không nằm trong ALLOWED_STATES | InvalidStateError      |
| state_name đã tồn tại trong registry      | DuplicateStateError    |
| target_state không nằm trong ALLOWED_STATES | InvalidStateError    |
| target_state chưa đăng ký (not registered) | InvalidTransitionError |

## reset_states Behavior
- Xóa toàn bộ registry (_states.clear())
- Reset current_state về None
- Sau reset, mọi transition_to sẽ raise InvalidTransitionError (vì không còn state nào registered)
- Thread-safe qua Lock
spec
fsm.md
