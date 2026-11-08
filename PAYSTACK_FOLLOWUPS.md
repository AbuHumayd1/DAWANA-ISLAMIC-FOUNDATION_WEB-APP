# Existing Paystack flow and small follow-up processor

Full launch now runs this processor automatically through Supervisor and
`run_dic_workers`; see [FULL_LAUNCH.md](FULL_LAUNCH.md). No external scheduler is
needed for that mode. The bounded command below remains available for diagnostics.

No payment platform or broker is added. Existing server fees, checkout, signatures,
independent verification and settlement remain authoritative. Settlement now writes
existing HousingJob rows in the same transaction as paid/confirmed. Queue uniqueness
prevents duplicate work. Allocation stays outside payment locks and uses the existing
approved group/capacity policy. Failed downstream processing never changes payment.

Registration already creates enrollment/account bindings; verified settlement makes
ordinary bookings eligible through existing portal checks. No second account is
created after payment. Email proof is still required. Initial verification delivery
now records a due time on PortalAccount before its after-commit attempt. Failures
retry with bounded backoff up to five attempts; password-protected resend remains
available. Delivery retries may repeat a verification link after an uncertain send;
links cannot change payment or bypass one-time email proof. Existing OTP workers
retain their separate uncertain-send safeguards.

Migration 0037 adds three retry/delivery fields to existing models. It has not been
executed. Apply it only through a separately approved database release before using
this code with the application enabled. Website-only mode stays enabled by default
and needs no registration tables for its public frontend.

After a separately approved application release, schedule this bounded command on
the existing runtime (for example once each minute with a provider scheduler):

```
python manage.py process_dic_followups --edition <id> --actor <authorized-service-user-id> --database-name <exact-name> --limit 50
```

The actor needs only the existing housing processing/allocation permissions. It is
configured once, not selected by participants. The command refuses website-only
mode and mismatched database confirmation, discovers missed existing paid bookings,
processes the existing housing queue, and retries due account-verification delivery.
It does not initialize charges, call Paystack, create schema or activate live mode.
No Redis, Celery, Kafka or additional data service is needed. A recurring invocation
is required; setting flags alone does not run it. This change configures no scheduler.

Policy/capacity/guardian conflicts remain held for exceptional review. Temporary
database/lock failures retry with bounded backoff. Unknown failures remain failed
for investigation; supervised releases are never automatically undone. Existing
guardian approval and tutor accommodation policies are unchanged. Complimentary
tutors remain on their authorized no-payment path and outside camper housing.

The frontend uses the existing Paystack checkout and return route. Verified return
status now separately reports housing pending/review and portal delivery/verification.
Payment remains confirmed while those steps are delayed. Account delivery is not
account provisioning. No passwords or payment credentials are returned in status.

Live payments remain disabled by the existing website-only and Paystack activation
gates. Essential PostgreSQL settlement/concurrency/retry tests and owner activation
approval are still required. ZevCloud ingress/database TLS gates also remain. Its
documented SMTP restriction requires a supported HTTPS email backend before portal
delivery can be accepted; no email infrastructure is provisioned by this change.
