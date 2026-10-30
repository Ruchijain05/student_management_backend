USE student_management;

ALTER TABLE fee_payments
    ADD COLUMN idempotency_key CHAR(36) NULL,
    ADD UNIQUE KEY uq_fee_payments_idempotency_key (idempotency_key);
