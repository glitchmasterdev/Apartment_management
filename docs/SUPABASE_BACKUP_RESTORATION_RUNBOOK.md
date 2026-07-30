# Supabase backup and restoration runbook

This repository contains no evidence that backups, PITR, or restoration tests
are enabled. Do not state that they are enabled until an authorized project
administrator verifies the Supabase dashboard and records the result.

1. An authorized owner checks the Supabase dashboard plan and backup/PITR
   availability, then documents the retention period and responsible person.
2. Before a restoration, place the application in maintenance mode, record the
   incident window, and preserve audit logs.
3. Restore into a separate project/branch first. Apply the schema migrations,
   validate RLS as landlord, caretaker, and two distinct tenant users, and
   verify storage-object access.
4. Reconcile tenant, payment, lease, and maintenance counts against a known
   report. Obtain owner approval before any production cutover.
5. Record the restore point, verification evidence, time to restore, and any
   data gap. Schedule a periodic non-production restoration drill.
