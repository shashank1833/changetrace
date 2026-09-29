# Payment Policies and Architecture

## State Machine
The payment record transitions through strict states:
`INITIALIZED` -> `AUTHORIZED` -> `SETTLING` -> `SETTLED`.

Settled payments may only transition to `REFUNDED` or `DISPUTED`.

## Fee Schedule
- Standard card processing fee is 2.9% plus $0.30 fixed interchange.
- Multi-currency transactions carry an extra 1.0% foreign exchange processing fee.
- The 30 cent fixed fee is non-refundable by interchange rules upon customer refund.
