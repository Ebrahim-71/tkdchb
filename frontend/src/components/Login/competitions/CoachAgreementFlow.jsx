// src/components/Login/competitions/CoachAgreementFlow.jsx
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import {
  // مشترک
  getCompetitionTerms,
  getCurrentRole,
  // کیوروگی
  getCoachApprovalStatus,
  approveCompetition,
  // پومسه
  getPoomsaeCoachApprovalStatus,
  approvePoomsaeCompetition,
} from "../../../api/competitions";
import "./CoachAgreementFlow.css";

const toFa = (s) => String(s ?? "").replace(/\d/g, (d) => "۰۱۲۳۴۵۶۷۸۹"[d]);

function isKyorugi(competition) {
  const s = String(competition?.style_display || competition?.style || competition?.type || "")
    .trim()
    .toLowerCase();
  return s.includes("کیوروگی") || s.includes("kyorugi") || s.includes("kyor");
}

export default function CoachAgreementFlow({ competition, onDone, onCancel }) {
  const navigate = useNavigate();
  const publicId = competition?.public_id || competition?.id;
  const ky = isKyorugi(competition);
  
  // ---- UI ----
  const [loading, setLoading] = useState(true);
  const [step, setStep] = useState("terms"); // "terms" | "code"
  const slug = competition?.slug || competition?.slug_str || competition?.slug_text || null;

  // ---- data ----
  const [approved, setApproved] = useState(false);
  const [code, setCode] = useState(null);
  const [coachName, setCoachName] = useState("—");
  const [clubNames, setClubNames] = useState([]);
  const [termsTitle, setTermsTitle] = useState("تعهدنامه مربی");
  const [terms, setTerms] = useState("");

  // ---- inputs/network ----
  const [checked, setChecked] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  // فقط برای سازگاری قدیمی نگهش می‌داریم، اما دیگر در goToDetails استفاده نمی‌کنیم
  const getRoleSegment = () => {
    const raw =
      (getCurrentRole && getCurrentRole()) ||
      localStorage.getItem("user_role") ||
      "";
    const r = String(raw).toLowerCase();
    if (r === "both") return "coach";
    if (["coach", "player", "referee", "club", "heyat", "board"].includes(r))
      return r;
    if (r.includes("coach")) return "coach";
    if (r.includes("referee")) return "referee";
    if (r.includes("club")) return "club";
    if (r.includes("heyat") || r.includes("board")) return "heyat";
    if (r.includes("player")) return "player";
    return "coach";
  };

  // ✅ بعد از تأیید برو به جزئیات مسابقه (دیسیپلین-محور)
const goToDetails = () => {
  const targetKey = competition?.slug || competition?.public_id || competition?.id;
  if (!targetKey) {
    alert("شناسه مسابقه در دسترس نیست. لطفاً از لیست مسابقات وارد شوید.");
    return;
  }

  const roleSeg = getRoleSegment();
  const discipline = isKyorugi(competition) ? "kyorugi" : "poomsae";
  const target = `/dashboard/${roleSeg}/competitions/${discipline}/${encodeURIComponent(targetKey)}`;

  navigate(target);
  onDone?.(targetKey);
};


  useEffect(() => {
    let alive = true;

    async function bootstrap() {
      if (!publicId) return;
      setLoading(true);
      setError("");

      try {
        // 1) متن تعهدنامه
        try {
          const det = await getCompetitionTerms(publicId);
          if (!alive) return;
          setTermsTitle((det?.title || "تعهدنامه مربی").trim());
          setTerms(
            (det?.content || det?.html || det?.text || "").trim() ||
              "با پذیرش این تعهدنامه، مسئولیت‌های مربی/نماینده را می‌پذیرم."
          );
        } catch {
          if (!alive) return;
          setTermsTitle("تعهدنامه مربی");
          setTerms(
            "با پذیرش این تعهدنامه، مسئولیت‌های مربی/نماینده را می‌پذیرم."
          );
        }

        // 2) وضعیت تایید + کد
        try {
          const st = ky
            ? await getCoachApprovalStatus(publicId)
            : await getPoomsaeCoachApprovalStatus(publicId);

          if (!alive) return;

          const ok = !!st?.approved || !!st?.is_active || !!st?.terms_accepted;
          setApproved(ok);
          setCode(st?.code || null);
          setCoachName(st?.coach_name || "—");
          setClubNames(Array.isArray(st?.club_names) ? st.club_names : []);
          setStep(ok ? "code" : "terms");
        } catch (e) {
          if (!alive) return;
          setError(e?.message || "خطا در دریافت وضعیت مربی");
          setStep("terms");
        }
      } finally {
        if (alive) setLoading(false);
      }
    }

    bootstrap();
    return () => {
      alive = false;
    };
  }, [publicId, ky]);

  const handleApprove = async () => {
    if (!checked || !publicId) return;
    setSubmitting(true);
    setError("");

    try {
      const res = ky
        ? await approveCompetition(publicId)
        : await approvePoomsaeCompetition(publicId);

      setApproved(true);
      setStep("code");

      if (res?.code) {
        setCode(res.code);
      } else {
        // fallback: دوباره وضعیت را بگیر
        await new Promise((r) => setTimeout(r, 200));
        try {
          const st = ky
            ? await getCoachApprovalStatus(publicId)
            : await getPoomsaeCoachApprovalStatus(publicId);
          setCode(st?.code || null);
        } catch {
          setCode(null);
        }
      }
    } catch (e) {
      setError(e?.message || "خطا در تایید تعهدنامه");
    } finally {
      setSubmitting(false);
    }
  };

  const refreshCode = async () => {
    setSubmitting(true);
    setError("");
    try {
      setStep("code");
      const st = ky
        ? await getCoachApprovalStatus(publicId)
        : await getPoomsaeCoachApprovalStatus(publicId);
      const ok = !!st?.approved || !!st?.is_active || !!st?.terms_accepted;
      setApproved(ok);
      setCode(st?.code || null);
    } catch (e) {
      setError(e?.message || "خطا در دریافت کد");
    } finally {
      setSubmitting(false);
    }
  };

  const copyCode = async () => {
    try {
      await navigator.clipboard.writeText(String(code || ""));
      alert("کد کپی شد.");
    } catch {
      window.prompt("برای کپی، کد را انتخاب و کپی کنید:", String(code || ""));
    }
  };

  const Modal = ({ children }) => (
    <div className="modal-overlay" onClick={onCancel}>
      <div className="modal-card" onClick={(e) => e.stopPropagation()}>
        {children}
      </div>
    </div>
  );

  if (loading) return null;

  return (
    <Modal>
      <h3 className="modal-title">
        {step === "terms" ? (
          <>
            {termsTitle} «{(competition?.title || competition?.name || "—") || "—"}»
          </>
        ) : (
          "کد تأیید مربی"
        )}
      </h3>

      {!!error && <div className="alert-error">{error}</div>}

      {step === "terms" ? (
        <>
          <div className="modal-meta">
            <div>
              <b>مربی:</b> {coachName}
            </div>
            <div>
              <b>باشگاه‌ها:</b>{" "}
              {clubNames?.length ? clubNames.join("، ") : "—"}
            </div>
          </div>

          <div className="modal-text" style={{ whiteSpace: "pre-line" }}>
            {terms || "برای این مسابقه قالب تعهدنامه انتخاب نشده است."}
          </div>

          <label className="modal-check">
            <input
              type="checkbox"
              checked={checked}
              onChange={(e) => setChecked(e.target.checked)}
            />
            <span>تمام موارد بالا را تأیید می‌کنم</span>
          </label>

          <div className="modal-actions">
            <button className="btn btn-secondary" onClick={onCancel}>
              انصراف
            </button>
            <button
              className="btn btn-success"
              disabled={!checked || submitting}
              onClick={handleApprove}
              title={!checked ? "ابتدا تعهدنامه را بپذیرید" : ""}
            >
              {submitting ? "در حال ثبت…" : "تأیید"}
            </button>
          </div>
        </>
      ) : (
        <>
          {approved && code ? (
            <>
              <p className="modal-code">
                کد تأیید شما <b>{toFa(String(code))}</b> است.
                <br />
                لطفاً این کد را برای ثبت‌نام بازیکنان خود استفاده کنید.
              </p>
              <div className="modal-actions" style={{ gap: 8 }}>
                <button className="btn btn-outline" onClick={copyCode}>
                  کپی کد
                </button>
                <button className="btn btn-success" onClick={goToDetails}>
                  ادامه
                </button>
              </div>
            </>
          ) : (
            <>
              <p className="modal-code">تأیید انجام شد، اما کدی دریافت نشد.</p>
              <div className="modal-actions" style={{ gap: 8 }}>
                <button
                  className="btn btn-outline"
                  onClick={refreshCode}
                  disabled={submitting}
                >
                  {submitting ? "در حال دریافت…" : "تازه‌سازی کد"}
                </button>
                <button className="btn btn-success" onClick={goToDetails}>
                  ادامه
                </button>
              </div>
            </>
          )}
        </>
      )}
    </Modal>
  );
}
