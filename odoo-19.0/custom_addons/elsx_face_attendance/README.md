# ELSx Face Attendance

Optional facial verification for Odoo Attendances.

Recognition engine:

- Local Docker sidecar, no cloud biometric API.
- Hybrid OpenCV descriptor using face detection, eye-assisted alignment, LBP, DCT, and gradient features.
- Multi-frame enrollment and verification from the browser for better quality and passive capture checks.
- Quality scoring warns on blurry, dark, distant, off-center, or multi-face captures.
- Backward-compatible with older single-vector enrolled profiles.

Safety defaults:

- The addon is installable but not auto-installed.
- Face attendance is disabled after install.
- Normal `hr_attendance` check-in/check-out remains unchanged until an admin enables a face policy.
- The Docker face sidecar is behind the `face` Compose profile and is not started by normal `docker compose up -d --build`.
- The addon stores encrypted embeddings and verification metadata. It does not store raw face images by default.

High-assurance mode:

- Adds a strict policy option named `High Assurance Verification`.
- Requires face match, passive liveness/motion status, browser challenge completion, minimum usable samples, minimum quality, GPS evidence, and hashed device evidence.
- Produces a risk score, risk level, decision, manual-review flag, device evidence hash, challenge id/status, and evidence summary in the verification log.
- Keeps raw face images out of Odoo by default; only encrypted embeddings and audit metadata are stored.
- This is a high-assurance software workflow. It is not a defence/government certification claim by itself. Certified biometric hardware, controlled capture stations, independent spoof testing, and formal compliance review are still required for regulated environments.

Operating modes on the attendance page:

- `Manual Verify`: camera capture is manual and the user clicks Check In / Out.
- `Auto Person Scan`: continuously scans for one stable person and prepares verification, but leaves the attendance action manual.
- `Room Monitor`: scans room/person presence and quality only. It never changes attendance.
- `Auto Verify`: after a stable one-person scan, starts the normal secure challenge and attendance flow, then applies a cooldown to prevent repeated check-in/out toggles.

Recommended rollout:

1. Restore a staging copy of `FiberaFRP_DB`.
2. Install/upgrade `elsx_face_attendance`.
3. Start the sidecar only on staging:

   ```bash
   docker compose --profile face up -d face_sidecar
   ```

4. Open Settings > Face Attendance and keep mode as `Audit Only`.
5. Enroll a small internal test group.
6. Test normal Attendances, face attendance, GPS/IP capture, and logs.
7. Enable production only after written approval.

Production update command:

```bash
read -s -p "Backup passphrase: " BACKUP_PASSPHRASE
echo
export BACKUP_PASSPHRASE
bash deploy/safe_production_update.sh FiberaFRP_DB
```

Do not use `docker compose down -v` on production.
