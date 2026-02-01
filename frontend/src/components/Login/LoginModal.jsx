// src/components/auth/LoginModal.jsx
import React, { useEffect, useRef, useState } from "react";
import "./LoginModal.css";
import { Eye, EyeOff } from "lucide-react";
import { useNavigate } from "react-router-dom";

// ---------- تنظیمات API ----------
const API_BASE = "https://api.chbtkd.ir";   // آدرس API روی سرور
const ACCOUNTS_PREFIX = "/api/auth/";       // prefix برای auth (طبق بک‌اند)

// ساخت آدرس نهایی (جلوگیری از // اضافه وسط آدرس)
const joinUrl = (...parts) =>
  parts
    .map((p, i) =>
      i === 0
        ? String(p || "").replace(/\/+$/, "")
        : String(p || "").replace(/^\/+|\/+$/g, "")
    )
    .filter(Boolean)
    .join("/");

const PATHS = {
  login: "login", // بدون / آخر
};

// ---------- نقش‌ها ----------
const ROLE_GROUPS = {
  player: ["player"],
  coachref: ["coach", "referee", "both"],
  club: ["club"],
  heyat: ["heyat"],
};

// ---------- توابع کمکی ----------
const normalizeDigits = (s = "") => {
  const fa = "۰۱۲۳۴۵۶۷۸۹";
  const ar = "٠١٢٣٤٥٦٧٨٩";
  return String(s)
    .trim()
    .replace(/[۰-۹]/g, (d) => String(fa.indexOf(d)))
    .replace(/[٠-٩]/g, (d) => String(ar.indexOf(d)))
    .replace(/[\s-]/g, "");
};

const isValidUsername = (v = "") => {
  const val = normalizeDigits(v);
  if (/^\+?\d+$/.test(val)) {
    const digits = val.replace(/^\+/, "");
    return digits.length >= 10 && digits.length <= 15;
  }
  return val.length >= 3;
};

const normalizeRole = (r = "") => {
  const key = String(r || "").toLowerCase();
  if (["player"].includes(key)) return "player";
  if (["coach", "referee", "both"].includes(key)) return key;
  if (["club"].includes(key)) return "club";
  if (["heyat", "hey'at"].includes(key)) return "heyat";
  return "player";
};

// ---------- کامپوننت اصلی ----------
const LoginModal = ({
  role = "player",
  title,
  subtitle,
  onClose,
  onForgotPassword,
}) => {
  const navigate = useNavigate();
  const allowed = ROLE_GROUPS[role] || ["player"];

  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const abortRef = useRef(null);
  const cardRef = useRef(null);
  const userInputRef = useRef(null);

  // قفل اسکرول پشت مودال و فوکوس
  useEffect(() => {
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    setTimeout(() => userInputRef.current?.focus(), 0);
    return () => {
      document.body.style.overflow = prev;
      if (abortRef.current) abortRef.current.abort();
    };
  }, []);

  // کلیدهای Esc و Enter
  useEffect(() => {
    const onKey = (e) => {
      if (e.key === "Escape" && !loading) onClose?.();
      if (e.key === "Enter" && !loading) {
        const form = document.getElementById("login-form");
        if (form) form.requestSubmit();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [loading, onClose]);

  const handleBackdropClick = (e) => {
    if (loading) return;
    if (cardRef.current && !cardRef.current.contains(e.target)) onClose?.();
  };

  // ---------- ورود ----------
  const handleLogin = async (e) => {
    e.preventDefault();
    if (loading) return;

    setError("");
    const u = normalizeDigits(username || "");
    const p = String(password || "").trim();

    if (!u || !p) return setError("نام کاربری و رمز عبور الزامی است.");
    if (!isValidUsername(u)) return setError("فرمت نام کاربری صحیح نیست.");
    if (p.length < 6) return setError("حداقل طول رمز عبور ۶ کاراکتر است.");

    setLoading(true);
    const controller = new AbortController();
    abortRef.current = controller;

    try {
      // https://api.chbtkd.ir/api/auth/login/
      const url = joinUrl(API_BASE, ACCOUNTS_PREFIX, PATHS.login) + "/";
      console.log("[LOGIN] POST", url);

      const res = await fetch(url, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Role-Group": role,
        },
        credentials: "include",
        signal: controller.signal,
        body: JSON.stringify({
          identifier: u,
          password: p,
          roleGroup: role,
        }),
      });

      let data = {};
      try {
        data = await res.json();
      } catch (_) {}

      if (!res.ok) {
        console.error("LOGIN_ERROR", res.status, data);
        const msg =
          data?.error ||
          data?.detail ||
          data?.message ||
          (res.status === 401
            ? "نام کاربری یا رمز عبور اشتباه است."
            : res.status === 403
            ? "این فرم مخصوص نقش دیگری است."
            : res.status === 404
            ? "مسیر لاگین یافت نشد."
            : "مشکلی در ورود پیش آمد.");
        throw new Error(msg);
      }

      const roleFromAPI = normalizeRole(
        data.role || data.user?.role || "player"
      );
      const token =
        data.access || data.token || data.jwt || data.accessToken;

      const okCoachRef =
        role === "coachref" &&
        ["coach", "referee", "both"].includes(roleFromAPI);
      if (!allowed.includes(roleFromAPI) && !okCoachRef) {
        throw new Error(
          "این فرم مخصوص نقش دیگری است. لطفاً از فرم صحیح ورود استفاده کنید."
        );
      }

      if (token) localStorage.setItem(`${roleFromAPI}_token`, token);
      localStorage.setItem("user_role", roleFromAPI);

      onClose?.();
      const nextPath =
        roleFromAPI === "player"
          ? "/dashboard/player"
          : roleFromAPI === "club"
          ? "/dashboard/club"
          : roleFromAPI === "heyat"
          ? "/dashboard/heyat"
          : "/dashboard/coachref";
      navigate(nextPath);
    } catch (err) {
      if (err.name !== "AbortError") {
        setError(err.message || "مشکلی پیش آمد.");
      }
    } finally {
      setLoading(false);
      abortRef.current = null;
    }
  };

  // ---------- فراموشی رمز ----------
  const handleForgotClick = (e) => {
    e.preventDefault();
    if (loading) return;
    onClose?.();
    onForgotPassword?.();
  };

  return (
    <div className="login-modal-backdrop" onMouseDown={handleBackdropClick}>
      <div
        className="login-modal-container"
        dir="rtl"
        ref={cardRef}
        onMouseDown={(e) => e.stopPropagation()}
      >
        <button
          className="login-close-btn"
          onClick={onClose}
          disabled={loading}
          aria-label="بستن"
        >
          &times;
        </button>

        <div className="login-modal-content">
          <h2>{title || "ورود به پنل کاربری"}</h2>
          <p className="login-subtext">
            {subtitle || "لطفاً نام کاربری و رمز عبور را وارد کنید."}
          </p>

          <form
            id="login-form"
            onSubmit={handleLogin}
            className="login-form"
            noValidate
          >
            <input
              ref={userInputRef}
              className="login-input-field"
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder="نام کاربری (شماره موبایل)"
              dir="ltr"
              autoComplete="username"
            />

            <div className="login-password-container">
              <input
                className="login-password-input"
                type={showPassword ? "text" : "password"}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="رمز عبور"
                dir="ltr"
                autoComplete="current-password"
              />
              <button
                type="button"
                className="login-toggle-password-btn"
                onClick={() => setShowPassword((s) => !s)}
                disabled={loading}
              >
                {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
              </button>
            </div>

            {error && <p className="login-error-msg">{error}</p>}

            <button
              type="submit"
              className="login-action-btn"
              disabled={loading}
            >
              {loading ? "در حال ورود..." : "ورود"}
            </button>
          </form>

          <button
            type="button"
            className="login-resend-btn"
            onClick={handleForgotClick}
            disabled={loading}
          >
            فراموشی رمز عبور
          </button>
        </div>
      </div>
    </div>
  );
};

export default LoginModal;
