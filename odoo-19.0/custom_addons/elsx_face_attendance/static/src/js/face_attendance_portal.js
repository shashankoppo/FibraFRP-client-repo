(function () {
    "use strict";

    if (window.__elsxFaceAttendancePortalLoaded) {
        return;
    }
    window.__elsxFaceAttendancePortalLoaded = true;

    function ready(callback) {
        if (document.readyState === "loading") {
            document.addEventListener("DOMContentLoaded", callback, {once: true});
            return;
        }
        callback();
    }

    ready(function () {
        function installKioskLinkHandler() {
            document.addEventListener("click", function (event) {
                const link = event.target.closest(".elsx_face_kiosk_link");
                if (!link) {
                    return;
                }
                event.preventDefault();
                const token = link.dataset.token;
                if (!token) {
                    return;
                }
                const currentParams = new URLSearchParams(window.location.search);
                const target = new URL("/elsx_face_attendance/kiosk/" + encodeURIComponent(token), window.location.origin);
                const dbName = currentParams.get("db");
                if (dbName) {
                    target.searchParams.set("db", dbName);
                }
                if (currentParams.get("from_trial_mode")) {
                    target.searchParams.set("from_trial_mode", currentParams.get("from_trial_mode"));
                }
                window.location.href = target.toString();
            });
        }

        installKioskLinkHandler();

        const root = document.querySelector(".elsx_face_attendance_page");
        if (!root) {
            return;
        }

        const isKiosk = root.classList.contains("elsx_face_kiosk_page");
        const statusEl = document.getElementById("elsx_face_status");
        const resultEl = document.getElementById("elsx_face_result");
        const liveHintEl = document.getElementById("elsx_face_live_hint");
        const challengeEl = document.getElementById("elsx_face_challenge");
        const policyEl = document.getElementById("elsx_face_policy");
        const deviceEl = document.getElementById("elsx_face_device");
        const riskEl = document.getElementById("elsx_face_risk");
        const evidenceEl = document.getElementById("elsx_face_evidence");
        const scanPanel = document.getElementById("elsx_face_scan_panel");
        const scanStateEl = document.getElementById("elsx_face_scan_state");
        const scanCountEl = document.getElementById("elsx_face_scan_count");
        const scanQualityEl = document.getElementById("elsx_face_scan_quality");
        const scanActionEl = document.getElementById("elsx_face_scan_action");
        const gateSystemEl = document.getElementById("elsx_face_gate_system");
        const gateCameraEl = document.getElementById("elsx_face_gate_camera");
        const gateIdentityEl = document.getElementById("elsx_face_gate_identity");
        const gatePolicyEl = document.getElementById("elsx_face_gate_policy");
        const modeTitleEl = document.getElementById("elsx_face_mode_title");
        const modeBodyEl = document.getElementById("elsx_face_mode_body");
        const modeGuardEl = document.getElementById("elsx_face_mode_guard");
        const metricStabilityEl = document.getElementById("elsx_face_metric_stability");
        const metricConfidenceEl = document.getElementById("elsx_face_metric_confidence");
        const metricLivenessEl = document.getElementById("elsx_face_metric_liveness");
        const metricCooldownEl = document.getElementById("elsx_face_metric_cooldown");
        const stepCameraEl = document.getElementById("elsx_face_step_camera");
        const stepScanEl = document.getElementById("elsx_face_step_scan");
        const stepChallengeEl = document.getElementById("elsx_face_step_challenge");
        const stepDecisionEl = document.getElementById("elsx_face_step_decision");
        const modeButtons = Array.prototype.slice.call(root.querySelectorAll("[data-face-mode]"));
        const video = document.getElementById("elsx_face_video");
        const canvas = document.getElementById("elsx_face_canvas");
        const startBtn = document.getElementById("elsx_face_start");
        const checkBtn = document.getElementById("elsx_face_check");
        const enrollBtn = document.getElementById("elsx_face_enroll");

        let stream = null;
        let status = {};
        let scanMode = "manual";
        let scanTimer = null;
        let scanBusy = false;
        let stableSingleFace = 0;
        let verificationBusy = false;
        let autoCooldownUntil = 0;

        const modeLabels = {
            manual: "Manual Verify",
            person_auto: "Auto Person Scan",
            room_monitor: "Room Monitor",
            auto_verify: "Auto Verify",
        };

        const modeProfiles = {
            manual: {
                title: "Manual Verification",
                body: "The operator starts check-in/out after confirming the person, camera frame, and policy state.",
                guard: "Best for reception, HR desk, or controlled supervisor-driven attendance.",
            },
            person_auto: {
                title: "Auto Person Scan",
                body: "The scanner tracks one stable person and prepares verification, but attendance is still confirmed manually.",
                guard: "Useful for front desks where the system should guide the operator without auto toggling attendance.",
            },
            room_monitor: {
                title: "Room Monitor",
                body: "The camera estimates visible face count and quality without changing attendance records.",
                guard: "Observation mode only. It never creates check-in or check-out entries.",
            },
            auto_verify: {
                title: "Auto Verify",
                body: "After one clear face remains stable, the system runs challenge verification and updates attendance.",
                guard: "Use only at a controlled kiosk. Cooldown prevents repeated toggles.",
            },
        };

        function setText(element, value) {
            if (element) {
                element.textContent = value || "";
            }
        }

        function setPanelState(element, state, label) {
            if (!element) {
                return;
            }
            element.className = element.className.replace(/\b(ok|warn|error|active)\b/g, "").trim();
            element.classList.add(state || "warn");
            const target = element.querySelector("span");
            if (target && label !== undefined) {
                target.textContent = label;
            }
        }

        function setStep(element, state, label) {
            if (!element) {
                return;
            }
            element.className = "elsx_face_step " + (state || "warn");
            const target = element.querySelector("span");
            if (target && label !== undefined) {
                target.textContent = label;
            }
        }

        function cooldownSeconds() {
            return Math.max(0, Math.ceil((autoCooldownUntil - Date.now()) / 1000));
        }

        function updateCooldownMetric() {
            const remaining = cooldownSeconds();
            setText(metricCooldownEl, remaining ? remaining + "s lockout" : "Ready");
        }

        function updateModeSummary() {
            const profile = modeProfiles[scanMode] || modeProfiles.manual;
            setText(modeTitleEl, profile.title);
            setText(modeBodyEl, profile.body);
            setText(modeGuardEl, profile.guard);
        }

        function updateReadiness() {
            const hasStatus = Object.prototype.hasOwnProperty.call(status, "enabled");
            const identityReady = isKiosk ? Number(status.enrolled_count || 0) > 0 : !!status.face_enrolled;
            setPanelState(
                gateSystemEl,
                !hasStatus ? "warn" : status.enabled ? "ok" : "error",
                !hasStatus ? "Checking" : status.enabled ? "Enabled" : "Disabled"
            );
            setPanelState(gateCameraEl, stream ? "ok" : "warn", stream ? "Camera active" : "Not started");
            setPanelState(
                gateIdentityEl,
                !hasStatus ? "warn" : identityReady ? "ok" : "warn",
                !hasStatus
                    ? "Pending"
                    : isKiosk
                    ? ((status.enrolled_count || 0) + " enrolled")
                    : (status.face_enrolled ? "Face enrolled" : "No face profile")
            );
            setPanelState(
                gatePolicyEl,
                !hasStatus ? "warn" : status.high_assurance ? "active" : "ok",
                !hasStatus ? "Loading" : status.high_assurance ? "High assurance" : ((status.mode || "audit_only").replaceAll("_", " "))
            );
            updateCooldownMetric();
        }

        function updateMetrics(data) {
            const payload = data || {};
            const stabilityLabel = stableSingleFace >= 3 ? "Locked" : stableSingleFace + "/3 stable scans";
            setText(metricStabilityEl, stabilityLabel);
            if (payload.quality !== undefined) {
                const quality = Math.round(Number(payload.quality || 0) * 100);
                setText(metricLivenessEl, quality + "% " + (payload.quality_status || "capture quality"));
            }
            if (payload.confidence !== undefined) {
                setText(metricConfidenceEl, Math.round(Number(payload.confidence || 0) * 100) + "% match");
            }
            updateCooldownMetric();
        }

        function showResult(message, type) {
            if (!resultEl) {
                return;
            }
            resultEl.textContent = message || "";
            resultEl.className = "elsx_face_result " + (type || "");
        }

        function setHint(message, type) {
            if (!liveHintEl) {
                return;
            }
            liveHintEl.textContent = message || "";
            liveHintEl.className = "elsx_face_live_hint " + (type || "");
        }

        function setChallenge(message, type) {
            if (!challengeEl) {
                return;
            }
            challengeEl.textContent = message || "";
            challengeEl.className = "elsx_face_challenge " + (type || "");
        }

        function showEvidence(message) {
            if (!evidenceEl) {
                return;
            }
            evidenceEl.textContent = message || "";
            evidenceEl.className = "elsx_face_evidence " + (message ? "show" : "");
        }

        function updateScanPanel(payload, type) {
            const data = payload || {};
            const faceCount = Number(data.face_count || 0);
            const quality = Number(data.quality || 0);
            const qualityLabel = data.quality_status || "-";
            const warnings = data.warnings || [];
            if (scanPanel) {
                scanPanel.className = "elsx_face_scan_panel " + (type || "");
            }
            if (scanStateEl) {
                scanStateEl.textContent = data.state || data.scan_status || (modeLabels[scanMode] || "Scanner");
            }
            if (scanCountEl) {
                scanCountEl.textContent = data.face_count === undefined ? "-" : String(faceCount);
            }
            if (scanQualityEl) {
                scanQualityEl.textContent = data.quality === undefined
                    ? "-"
                    : Math.round(quality * 100) + "% " + qualityLabel;
            }
            if (scanActionEl) {
                scanActionEl.textContent = data.action || (warnings.length ? warnings.join(", ") : "Standby");
            }
            updateMetrics(data);
        }

        function sleep(ms) {
            return new Promise((resolve) => window.setTimeout(resolve, ms));
        }

        function deviceFingerprint() {
            const tz = (Intl.DateTimeFormat().resolvedOptions() || {}).timeZone || "";
            const screenInfo = window.screen ? [screen.width, screen.height, screen.colorDepth].join("x") : "";
            return [
                navigator.userAgent || "",
                navigator.platform || "",
                navigator.language || "",
                String(navigator.hardwareConcurrency || ""),
                screenInfo,
                tz,
            ].join("|");
        }

        function updateDecision(result) {
            if (riskEl) {
                if (!result) {
                    riskEl.textContent = "No verification yet";
                } else {
                    const risk = result.risk_level ? result.risk_level.replaceAll("_", " ") : "unknown";
                    const score = Number.isFinite(Number(result.risk_score)) ? Math.round(Number(result.risk_score)) : 0;
                    const decision = result.decision ? result.decision.replaceAll("_", " ") : (result.ok ? "allow" : "block");
                    riskEl.textContent = decision + " | " + risk + " risk | " + score + "/100";
                }
            }
            if (result && result.evidence_summary) {
                showEvidence(result.evidence_summary);
            }
            if (result) {
                updateMetrics(result);
                if (result.ok) {
                    setStep(stepDecisionEl, result.review_required ? "warn" : "ok", result.review_required ? "Review flagged" : "Attendance updated");
                } else {
                    setStep(stepDecisionEl, result.blocked ? "error" : "warn", result.error || "Decision blocked");
                }
            } else {
                setText(metricConfidenceEl, "No decision");
                setStep(stepDecisionEl, "warn", "No attendance action");
            }
        }

        async function rpc(route, params) {
            const response = await fetch(route, {
                method: "POST",
                headers: {"Content-Type": "application/json"},
                body: JSON.stringify({
                    jsonrpc: "2.0",
                    method: "call",
                    params: params || {},
                    id: Date.now(),
                }),
            });
            const payload = await response.json();
            if (payload.error) {
                throw new Error(payload.error.data && payload.error.data.message || payload.error.message || "Request failed");
            }
            return payload.result;
        }

        async function refreshStatus() {
            status = await rpc(
                isKiosk ? "/elsx_face_attendance/kiosk/status" : "/elsx_face_attendance/status",
                isKiosk ? {token: root.dataset.token} : {}
            );
            const pieces = [
                status.enabled ? "Enabled" : "Disabled by admin",
                "Policy: " + (status.mode || "audit_only").replaceAll("_", " "),
                isKiosk
                    ? ((status.enrolled_count || 0) + " enrolled employee(s)")
                    : (status.face_enrolled ? "Face enrolled" : "No face profile"),
            ];
            if (statusEl) {
                statusEl.textContent = pieces.join(" | ");
                statusEl.className = "elsx_face_status " + (status.enabled ? "ok" : "warn");
            }
            if (policyEl) {
                const high = status.high_assurance ? "High Assurance: " : "";
                policyEl.textContent = high + "threshold " + Math.round((status.threshold || 0) * 100) + "%, review " + Math.round((status.review_threshold || 0) * 100) + "%, min samples " + (status.min_samples || 3);
            }
            if (deviceEl) {
                deviceEl.textContent = status.require_device_fingerprint ? "Required and hashed in Odoo" : "Captured for audit when available";
            }
            setHint(status.enabled ? "Center your face inside the oval" : "Face Attendance is disabled by admin", status.enabled ? "ok" : "warn");
            setChallenge(status.high_assurance ? "High assurance challenge will run before check-in" : "Standard multi-frame verification", status.high_assurance ? "warn" : "ok");
            if (checkBtn) {
                checkBtn.disabled = !status.enabled || !stream || verificationBusy;
            }
            if (enrollBtn) {
                enrollBtn.disabled = !stream || !status.can_manage || verificationBusy;
            }
            updateReadiness();
            updateModeSummary();
        }

        function captureImage() {
            const width = video && video.videoWidth || 720;
            const height = video && video.videoHeight || 720;
            canvas.width = width;
            canvas.height = height;
            const ctx = canvas.getContext("2d");
            ctx.drawImage(video, 0, 0, width, height);
            return canvas.toDataURL("image/jpeg", 0.82);
        }

        function stopScanner() {
            if (scanTimer) {
                window.clearTimeout(scanTimer);
                scanTimer = null;
            }
            scanBusy = false;
            stableSingleFace = 0;
        }

        function scheduleScan(delay) {
            if (scanMode === "manual") {
                stopScanner();
                return;
            }
            if (!stream || scanBusy) {
                return;
            }
            if (scanTimer) {
                window.clearTimeout(scanTimer);
            }
            scanTimer = window.setTimeout(scanFrame, delay || 850);
        }

        function scannerMinimumQuality() {
            const configured = Number(status.min_quality || 0.52);
            return Math.max(0.48, Math.min(configured, 0.82));
        }

        async function scanFrame() {
            if (scanMode === "manual" || !stream || scanBusy) {
                return;
            }
            if (verificationBusy) {
                scheduleScan(1200);
                return;
            }
            scanBusy = true;
            setStep(stepScanEl, "active", "Scanning frame");
            try {
                const result = await rpc("/elsx_face_attendance/scan", {
                    token: root.dataset.token,
                    image: captureImage(),
                });
                if (!result.ok) {
                    throw new Error(result.error || "Face scan failed.");
                }
                const faceCount = Number(result.face_count || 0);
                const quality = Number(result.quality || 0);
                const minQuality = scannerMinimumQuality();
                let type = "warn";
                let action = "Waiting for one clear face.";
                if (!faceCount) {
                    stableSingleFace = 0;
                    action = "No clear face detected.";
                    setStep(stepScanEl, "warn", "No clear face");
                } else if (faceCount > 1) {
                    stableSingleFace = 0;
                    action = "Multiple people detected. Keep one person in frame for verification.";
                    setStep(stepScanEl, "warn", "Multiple people");
                } else if (quality < minQuality) {
                    stableSingleFace = 0;
                    action = (result.warnings || []).join(", ") || "Improve lighting, distance, or camera focus.";
                    setStep(stepScanEl, "warn", "Improve capture");
                } else {
                    stableSingleFace += 1;
                    type = stableSingleFace >= 3 ? "ok" : "warn";
                    action = stableSingleFace >= 3
                        ? "Single person locked. Verification ready."
                        : "Hold steady for " + (3 - stableSingleFace) + " more scan(s).";
                    setStep(stepScanEl, type, stableSingleFace >= 3 ? "Single person locked" : "Hold steady");
                }
                if (scanMode === "room_monitor") {
                    action = faceCount === 1
                        ? "Room monitor: one person visible. No attendance action will be taken."
                        : action;
                }
                if (scanMode === "person_auto" && stableSingleFace >= 3) {
                    setHint("Person locked - press Check In / Out when ready", "ok");
                }
                if (
                    scanMode === "auto_verify" &&
                    stableSingleFace >= 3 &&
                    status.enabled &&
                    Date.now() > autoCooldownUntil &&
                    !verificationBusy
                ) {
                    action = "Auto Verify is starting secure challenge.";
                    updateScanPanel(Object.assign({}, result, {
                        state: "Auto Verify",
                        action: action,
                    }), "ok");
                    checkAttendance({auto: true});
                    return;
                }
                updateScanPanel(Object.assign({}, result, {
                    state: modeLabels[scanMode] || "Scanner",
                    action: action,
                }), type);
            } catch (error) {
                stableSingleFace = 0;
                setStep(stepScanEl, "error", "Scan failed");
                updateScanPanel({
                    state: modeLabels[scanMode] || "Scanner",
                    action: error.message,
                }, "error");
            } finally {
                scanBusy = false;
                scheduleScan(scanMode === "room_monitor" ? 1100 : 850);
            }
        }

        function setScanMode(mode) {
            scanMode = mode || "manual";
            modeButtons.forEach(function (button) {
                button.classList.toggle("active", button.dataset.faceMode === scanMode);
            });
            updateModeSummary();
            updateReadiness();
            stopScanner();
            if (scanMode === "manual") {
                updateScanPanel({
                    state: "Manual mode standby",
                    action: stream ? "Press Check In / Out when ready." : "Start camera to scan",
                }, "");
                setStep(stepScanEl, "warn", "Manual standby");
                setHint(stream ? "Manual mode - center face before verification" : "Start camera and center your face", stream ? "ok" : "");
                return;
            }
            updateScanPanel({
                state: modeLabels[scanMode] || "Scanner",
                action: stream ? "Scanner warming up..." : "Start camera to begin automatic scanning.",
            }, "warn");
            setStep(stepScanEl, stream ? "active" : "warn", stream ? "Scanner warming up" : "Camera required");
            if (stream) {
                scheduleScan(250);
            }
        }

        async function startCamera() {
            if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
                showResult("Camera is not available in this browser.", "error");
                return;
            }
            try {
                setStep(stepCameraEl, "active", "Requesting permission");
                stream = await navigator.mediaDevices.getUserMedia({
                    video: {facingMode: "user", width: {ideal: 720}, height: {ideal: 720}},
                    audio: false,
                });
                video.srcObject = stream;
                showResult("Camera ready. Center the face inside the oval and keep only one person in frame.", "ok");
                setHint("Camera ready - hold steady", "ok");
                setStep(stepCameraEl, "ok", "Camera stream active");
                await refreshStatus();
                setScanMode(scanMode);
            } catch (error) {
                showResult("Camera permission failed: " + error.message, "error");
                setHint("Camera permission failed", "error");
                setStep(stepCameraEl, "error", "Permission failed");
                updateReadiness();
            }
        }

        async function requestChallenge(enrollment) {
            const challenge = await rpc("/elsx_face_attendance/challenge", {
                token: root.dataset.token,
                enrollment: !!enrollment,
            });
            if (!challenge.ok) {
                throw new Error(challenge.error || "Could not start verification challenge.");
            }
            setStep(stepChallengeEl, "active", "Challenge issued");
            return challenge;
        }

        async function captureChallengeSamples(enrollment) {
            const challenge = await requestChallenge(enrollment);
            const prompts = challenge.prompts || ["Hold steady"];
            const target = Math.max(1, challenge.sample_count || prompts.length || 3);
            const images = [];
            setChallenge("Challenge started", "warn");
            for (let index = 0; index < target; index += 1) {
                const prompt = prompts[index % prompts.length];
                setChallenge(prompt + " (" + (index + 1) + "/" + target + ")", "warn");
                setHint(prompt, "warn");
                await sleep(status.high_assurance ? 420 : 180);
                images.push(captureImage());
            }
            setChallenge("Challenge captured. Server is evaluating evidence.", "ok");
            setHint("Samples captured. Verifying locally...", "warn");
            setStep(stepChallengeEl, "ok", "Samples captured");
            return {
                images: images,
                challenge_id: challenge.challenge_id,
                challenge_status: images.length >= target ? "passed" : "incomplete",
                device_fingerprint: deviceFingerprint(),
            };
        }

        function currentLocation() {
            return new Promise((resolve) => {
                if (!navigator.geolocation) {
                    resolve({});
                    return;
                }
                navigator.geolocation.getCurrentPosition(
                    (position) => resolve({
                        latitude: position.coords.latitude,
                        longitude: position.coords.longitude,
                    }),
                    () => resolve({}),
                    {enableHighAccuracy: true, timeout: 6000, maximumAge: 60000}
                );
            });
        }

        async function checkAttendance(options) {
            const opts = options || {};
            if (!stream) {
                showResult("Start the camera first.", "warn");
                return;
            }
            if (verificationBusy) {
                return;
            }
            verificationBusy = true;
            if (checkBtn) {
                checkBtn.disabled = true;
            }
            if (enrollBtn) {
                enrollBtn.disabled = true;
            }
            showResult(opts.auto ? "Auto Verify locked one person. Running secure challenge..." : "Running secure face verification challenge...", "warn");
            updateDecision(false);
            setStep(stepDecisionEl, "active", "Evaluating");
            try {
                const evidence = await captureChallengeSamples(false);
                const images = evidence.images;
                const image = images[0];
                const location = await currentLocation();
                const result = await rpc(
                    isKiosk ? "/elsx_face_attendance/kiosk/check" : "/elsx_face_attendance/check",
                    Object.assign({
                        image: image,
                        images: images,
                        token: root.dataset.token,
                        device_fingerprint: evidence.device_fingerprint,
                        challenge_id: evidence.challenge_id,
                        challenge_status: evidence.challenge_status,
                    }, location)
                );
                updateDecision(result);
                if (!result.ok) {
                    showResult(result.error || "Face attendance was blocked.", result.blocked ? "error" : "warn");
                    setHint(result.error || "Verification failed", result.blocked ? "error" : "warn");
                    setChallenge(result.error || "Blocked", result.blocked ? "error" : "warn");
                } else {
                    const confidence = Math.round((result.confidence || 0) * 100);
                    const employee = result.employee_name ? (result.employee_name + " | ") : "";
                    const quality = result.quality_status ? (" | Quality: " + result.quality_status) : "";
                    const liveness = result.liveness_status ? (" | Capture: " + result.liveness_status.replaceAll("_", " ")) : "";
                    const review = result.review_required ? " | Manual review flagged" : "";
                    showResult(employee + (result.message || "Attendance updated.") + " Confidence: " + confidence + "%" + quality + liveness + review, result.review_required ? "warn" : result.verified ? "ok" : "warn");
                    setHint(result.review_required ? "Attendance updated, review required" : result.verified ? "Verified - attendance updated" : "Attendance updated in audit mode", result.review_required ? "warn" : result.verified ? "ok" : "warn");
                    setChallenge(result.review_required ? "Challenge complete, review flagged" : "Challenge passed", result.review_required ? "warn" : "ok");
                }
                await refreshStatus();
            } catch (error) {
                showResult(error.message, "error");
                setHint("Verification failed", "error");
                setStep(stepChallengeEl, "error", "Challenge failed");
                setStep(stepDecisionEl, "error", "Verification failed");
            } finally {
                verificationBusy = false;
                stableSingleFace = 0;
                if (opts.auto) {
                    autoCooldownUntil = Date.now() + 45000;
                    updateScanPanel({
                        state: "Auto Verify cooldown",
                        action: "Attendance action completed. Cooldown prevents repeated toggles.",
                    }, "ok");
                }
                if (checkBtn) {
                    checkBtn.disabled = !status.enabled || !stream;
                }
                if (enrollBtn) {
                    enrollBtn.disabled = !stream || !status.can_manage;
                }
                if (scanMode !== "manual") {
                    scheduleScan(opts.auto ? 4500 : 1200);
                }
                updateReadiness();
            }
        }

        async function enrollFace() {
            if (!stream) {
                showResult("Start the camera first.", "warn");
                return;
            }
            if (verificationBusy) {
                return;
            }
            verificationBusy = true;
            if (enrollBtn) {
                enrollBtn.disabled = true;
            }
            if (checkBtn) {
                checkBtn.disabled = true;
            }
            showResult("Capturing multiple enrollment samples. Keep your face centered and steady.", "warn");
            setStep(stepDecisionEl, "active", "Enrollment capture");
            try {
                const evidence = await captureChallengeSamples(true);
                const images = evidence.images;
                const image = images[0];
                const employeeId = root.dataset.employeeId;
                const result = await rpc("/elsx_face_attendance/enroll", {employee_id: employeeId, image: image, images: images});
                const detail = result.ok
                    ? " Quality: " + (result.quality_status || "captured") + " | Samples: " + (result.sample_count || images.length)
                    : "";
                showResult(result.ok ? (result.message + detail) : result.error, result.ok ? "ok" : "error");
                setHint(result.ok ? "Enrollment complete" : "Enrollment failed", result.ok ? "ok" : "error");
                setStep(stepDecisionEl, result.ok ? "ok" : "error", result.ok ? "Enrollment saved" : "Enrollment failed");
                await refreshStatus();
            } catch (error) {
                showResult(error.message, "error");
                setHint("Enrollment failed", "error");
                setStep(stepDecisionEl, "error", "Enrollment failed");
            } finally {
                verificationBusy = false;
                if (enrollBtn) {
                    enrollBtn.disabled = !stream || !status.can_manage;
                }
                if (checkBtn) {
                    checkBtn.disabled = !status.enabled || !stream;
                }
                if (scanMode !== "manual") {
                    scheduleScan(1200);
                }
                updateReadiness();
            }
        }

        modeButtons.forEach(function (button) {
            button.addEventListener("click", function () {
                setScanMode(button.dataset.faceMode || "manual");
            });
        });
        if (startBtn) {
            startBtn.addEventListener("click", startCamera);
        }
        if (checkBtn) {
            checkBtn.addEventListener("click", function () {
                checkAttendance();
            });
        }
        if (enrollBtn) {
            enrollBtn.addEventListener("click", enrollFace);
        }
        setScanMode("manual");
        window.setInterval(updateCooldownMetric, 1000);
        refreshStatus().catch((error) => {
            if (statusEl) {
                statusEl.textContent = "Could not load Face Attendance settings.";
                statusEl.className = "elsx_face_status warn";
            }
            showResult(error.message, "error");
            setPanelState(gateSystemEl, "error", "Settings failed");
        });
    });
})();
