# Kanban protocol

Work moves only across a declared transition edge and only when its entry policy is satisfied. Pull
work rather than silently exceeding WIP limits. Review may return work to delivery through the
declared rework edge. Use the operational block and resume actions so conditions and escalation
decisions remain attributed without inventing a board state.

A linked Delivery swarm may propose and collect bounded child work. Child acceptance and parent
service acceptance remain explicit, separately attributed decisions.

Delivery and Flow Manager roles may block and resume work. The Service Request Manager may cancel
work, reject child proposals under child authority, or cancel delegations under parent authority.
The Flow Manager may block and resume delegation flow.
