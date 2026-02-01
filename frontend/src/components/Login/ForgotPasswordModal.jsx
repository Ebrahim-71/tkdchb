// src/components/auth/ForgotPasswordModal.jsx
import React, { useEffect, useMemo, useState } from "react";
import "./LoginModal.css";

// آدرس پایه‌ی API فقط با متغیرهای محیطی CRA
const API_BASE = (
  process.env.REACT_APP_API_BASE_URL ||   // اگر تو .env تعریف کرده باشی
  process.env.REACT_APP_API_BASE ||       // برای سازگاری با اسم قدیمی‌تر
  "https://api.chbtkd.ir"                 // پیش‌فرض در توسعه
).replace(/\/+$/, "");                    // حذف اسلش‌های اضافی آخر

// endpoints درست
const SEND_URL   = `${API_BASE}/api/auth/password/forgot/send/`;
const VERIFY_URL = `${API_BASE}/api/auth/password/forgot/verify/`;


// نرمال‌سازی ارقام فارسی/عربی
const normalizeDigits = (s = "") => {
  const fa = "۰۱۲۳۴۵۶۷۸۹";
  const ar = "٠١٢٣٤٥٦٧٨٩";
  return String(s)
    .trim()
    .replace(/[۰-۹٠-٩]/g, (d) => {
      const iFa = fa.indexOf(d);
      if (iFa > -1) return String(iFa);
      const iAr = ar.indexOf(d);
      return iAr > -1 ? String(iAr) : d;
    });
};

const ForgotPasswordModal = ({ onClose }) => {
  const [step, setStep] = useState("phone"); // 'phone' | 'code' | 'result'
  const [phone, setPhone] = useState("");
  const [code, setCode] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null); // { username, password, role, message }

  const [cooldown, setCooldown] = useState(0);
  useEffect(() => {
    if (!cooldown) return;
    const t = setInterval(() => setCooldown((c) => (c > 0 ? c - 1 : 0)), 1000);
    return () => clearInterval(t);
  }, [cooldown]);

  // قفل اسکرول پشت مودال
  useEffect(() => {
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => (document.body.style.overflow = prev);
  }, []);

  const canResend = useMemo(() => cooldown === 0, [cooldown]);

  const handleSendCode = async (e) => {
    e?.preventDefault?.();
    setError("");

    const p = normalizeDigits(phone);
    if (!/^09\d{9}$/.test(p)) {
      setError("شماره موبایل معتبر نیست.");
      return;
    }

    setLoading(true);
    try {
      const res = await fetch(SEND_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ phone: p }),
      });
      const data = await res.json().catch(() => ({}));

      if (!res.ok) {
        if (res.status === 429 && typeof data.retry_after === "number") {
          setCooldown(Math.max(0, parseInt(data.retry_after, 10)));
        }
        throw new Error(data?.error || data?.detail || "ارسال کد ناموفق بود.");
      }

      setPhone(p);
      setStep("code");
      setCooldown(180);
    } catch (err) {
      setError(err.message || "مشکلی پیش آمد.");
    } finally {
      setLoading(false);
    }
  };

  const handleVerify = async (e) => {
    e?.preventDefault?.();
    setError("");

    const p = normalizeDigits(phone);
    const c = normalizeDigits(code);

    if (!/^09\d{9}$/.test(p)) {
      setError("شماره موبایل معتبر نیست.");
      return;
    }
    if (!/^\d{4}$/.test(c)) {
      setError("کد باید ۴ رقمی باشد.");
      return;
    }

    setLoading(true);
    try {
      const res = await fetch(VERIFY_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ phone: p, code: c }),
      });
      const data = await res.json().catch(() => ({}));

      if (!res.ok) {
        throw new Error(data?.error || data?.detail || "تأیید کد ناموفق بود.");
      }

      setResult({
        username: data.username,
        password: data.password,
        role: data.role,
        message: data.message || "رمز عبور شما بازنشانی شد.",
      });
      setStep("result");
    } catch (err) {
      setError(err.message || "مشکلی پیش آمد.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="login-modal-backdrop">
      <div className="login-modal-container" dir="rtl" role="dialog" aria-modal="true">
        <button className="login-close-btn" onClick={onClose} aria-label="بستن">
          &times;
        </button>

        <div className="login-modal-content">
          <h2>بازیابی رمز عبور</h2>

          {step === "phone" && (
            <>
              <p className="login-subtext">
                شماره موبایل خود را وارد کنید تا کد تأیید برایتان ارسال شود.
              </p>
              <form onSubmit={handleSendCode} className="login-form" noValidate>
                <input
                  className="login-input-field"
                  type="tel"
                  value={phone}
                  onChange={(e) => setPhone(e.target.value)}
                  placeholder="شماره موبایل (مثال: 0912xxxxxxx)"
                  dir="ltr"
                  inputMode="numeric"
                  autoFocus
                />
                {error && <p className="login-error-msg">{error}</p>}
                <button type="submit" className="login-action-btn" disabled={loading}>
                  {loading ? "در حال ارسال..." : "ارسال کد ۴ رقمی"}
                </button>
              </form>
            </>
          )}

          {step === "code" && (
                <>
                    <p className="login-subtext">
                    کد ۴ رقمی ارسال‌شده به {phone} را وارد کنید.
                    </p>

                    <form
                    onSubmit={handleVerify}
                    className="login-form"
                    style={{ textAlign: "center" }}
                    noValidate
                    >
                    <div
                        className="code-input-wrapper"
                        style={{
                        display: "flex",
                        justifyContent: "center",
                        gap: "10px",
                        marginBottom: "16px",
                        direction: "ltr",
                        }}
                    >
                        {[0, 1, 2, 3].map((i) => (
                        <input
                            key={i}
                            type="text"
                            inputMode="numeric"
                            maxLength="1"
                            className="code-input-box"
                            style={{
                            width: "50px",
                            height: "50px",
                            fontSize: "24px",
                            textAlign: "center",
                            border: "1px solid #ccc",
                            borderRadius: "8px",
                            }}
                            value={code[i] || ""}
                            onChange={(e) => {
                            const val = e.target.value.replace(/\D/g, "").slice(0, 1);
                            const newCode =
                                code.substring(0, i) + val + code.substring(i + 1);
                            setCode(newCode);

                            // فوکوس خودکار به بعدی
                            if (val && i < 3) {
                                const nextInput = e.target.parentNode.children[i + 1];
                                nextInput?.focus();
                            }
                            }}
                            onKeyDown={(e) => {
                            if (e.key === "Backspace" && !code[i] && i > 0) {
                                const prevInput = e.target.parentNode.children[i - 1];
                                prevInput?.focus();
                            }
                            }}
                        />
                        ))}
                    </div>

                    {error && <p className="login-error-msg">{error}</p>}

                    <button type="submit" className="login-action-btn" disabled={loading}>
                        {loading ? "در حال بررسی..." : "تأیید کد"}
                    </button>

                    <button
                        type="button"
                        className="login-resend-btn"
                        onClick={handleSendCode}
                        disabled={!canResend || loading}
                        style={{ marginTop: 8 }}
                    >
                        {canResend ? "ارسال مجدد کد" : `ارسال مجدد تا ${cooldown} ثانیه`}
                    </button>
                    </form>
                </>
                )}


          {step === "result" && result && (
            <div className="login-form">
              <p className="login-subtext" style={{ marginBottom: 12 }}>
                {result.message}
              </p>

              <div className="login-input-field" style={{ direction: "ltr" }}>
                <strong>نام کاربری:</strong> {result.username}
              </div>
              <div className="login-input-field" style={{ direction: "ltr" }}>
                <strong>رمزعبور:</strong> {result.password}
              </div>
            
              <button
                className="login-action-btn"
                onClick={onClose}
                style={{ marginTop: 12 }}
              >
                بستن
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default ForgotPasswordModal;
