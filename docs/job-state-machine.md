# Job State Machine

The job state machine prevents arbitrary status changes. All state changes should go through `JobService` or helpers in `job_state_machine`.

## Job Statuses

```text
QUEUED
RUNNING
WAITING_FOR_REVIEW
FAILED
RETRYABLE
CANCELLED
COMPLETED
```

## Valid Job Transitions

| From | To |
| --- | --- |
| `QUEUED` | `RUNNING`, `CANCELLED` |
| `RUNNING` | `WAITING_FOR_REVIEW`, `FAILED`, `RETRYABLE`, `CANCELLED`, `COMPLETED` |
| `WAITING_FOR_REVIEW` | `RUNNING`, `CANCELLED` |
| `FAILED` | `RETRYABLE`, `QUEUED` |
| `RETRYABLE` | `QUEUED`, `RUNNING`, `CANCELLED` |
| `CANCELLED` | terminal |
| `COMPLETED` | terminal |

## JobStep Statuses

```text
PENDING
RUNNING
WAITING_FOR_INPUT
FAILED
SKIPPED
COMPLETED
```

## Valid JobStep Transitions

| From | To |
| --- | --- |
| `PENDING` | `RUNNING`, `SKIPPED` |
| `RUNNING` | `WAITING_FOR_INPUT`, `FAILED`, `SKIPPED`, `COMPLETED` |
| `WAITING_FOR_INPUT` | `RUNNING`, `SKIPPED` |
| `FAILED` | `PENDING`, `RUNNING`, `SKIPPED` |
| `SKIPPED` | terminal |
| `COMPLETED` | terminal |

## Retry

Retry is allowed when:

- job status is `FAILED` or `RETRYABLE`
- `attempts < max_attempts`
- `retryable` is true

Retry moves the job to `QUEUED`, resets failed steps to `PENDING`, and clears the job error summary.

## Cancel

Cancel is allowed for any non-terminal job. It moves the job to `CANCELLED` and marks pending/running/waiting steps as `SKIPPED`.

## Resume

Resume is allowed from `WAITING_FOR_REVIEW` or `RETRYABLE`. Waiting steps can move back to `RUNNING`; retryable jobs can return to `QUEUED`.

## Enforcement

Invalid transitions raise explicit exceptions. ORM models do not contain business transition logic; state changes live in the service layer.

