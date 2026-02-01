// src/pages/payment/PaymentResult.jsx
import React, { useEffect, useMemo, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { API_BASE } from "../api/competitions";

/* ---------------- Query helper (robust) ---------------- */
function useQuery() {
  const { search } = useLocation();

  return useMemo(() => {
    if (!search) return new URLSearchParams("");

    // اگر چندتا ? داشتیم، همه‌ی ? بعد از اولی را & کن
    const firstQ = search.indexOf("?");
    if (firstQ === -1) return new URLSearchParams(search);

    const head = search.slice(0, firstQ + 1);
    const tail = search.slice(firstQ + 1).replace(/\?/g, "&");
    return new URLSearchParams(head + tail);
  }, [search]);
}

/* ---------------- Token helpers ---------------- */
const pickToken = () => {
  const role = (localStorage.getItem("user_role") || "").toLowerCase().trim();
  const roleTokenKey = role ? `${role}_token` : null;

  const keys = [
    "coach_token",
    "both_token",
    roleTokenKey,
    "access_token",
    "access",
    "auth_token",
    "token",
  ].filter(Boolean);

  for (const k of keys) {
    const v = localStorage.getItem(k);
    if (v) return v;
  }
  return null;
};

const authHeaders = () => {
  const t = pickToken();
  const h = { Accept: "application/json" };
  if (t) h.Authorization = `Bearer ${t}`;
  return h;
};

/* ---------------- helpers ---------------- */
const parseIds = (idsStr) => {
  if (!idsStr) return [];
  return String(idsStr)
    .split(",")
    .map((x) => Number(String(x).trim()))
    .filter((n) => Number.isFinite(n) && n > 0);
};

function pickDashboardRoleForFlow(flow) {
  const roleFromStorage = (localStorage.getItem("user_role") || "").toLowerCase().trim();
  if (String(flow || "").includes("bulk")) return roleFromStorage || "coach";
  return roleFromStorage || "player";
}

function pickKind({ flow, queryKind }) {
  const k = String(queryKind || "").toLowerCase().trim();
  if (k === "poomsae" || k === "kyorugi") return k;

  const f = String(flow || "").toLowerCase();
  if (f.includes("poomsae")) return "poomsae";
  if (f.includes("kyorugi")) return "kyorugi";

  // fallback: از آخرین انتخاب ذخیره شده (اختیاری)
  const last = (localStorage.getItem("last_payment_kind") || "").toLowerCase().trim();
  if (last === "poomsae" || last === "kyorugi") return last;

  return "kyorugi";
}

// تلاش برای گرفتن enrollment_ids از pid (هر دو مسیر intent/intents)
async function resolveEnrollmentIdsByPid(pid, kind) {
  if (!pid) return [];

  const cached = (localStorage.getItem("last_payment_enrollment_ids") || "").trim();
  if (cached) {
    const ids = parseIds(cached);
    if (ids.length) return ids;
  }

  const candidates = [
    `${API_BASE}/api/payments/intents/${encodeURIComponent(pid)}/enrollments/`,
    `${API_BASE}/api/payments/intent/${encodeURIComponent(pid)}/enrollments/`,
  ].map((u) => (kind ? `${u}?kind=${encodeURIComponent(kind)}` : u));

  for (const url of candidates) {
    try {
      const res = await fetch(url, {
        method: "GET",
        headers: authHeaders(),
        credentials: "omit",
      });
      if (!res.ok) continue;

      const data = await res.json().catch(() => null);
      const raw = Array.isArray(data?.enrollment_ids) ? data.enrollment_ids : [];
      const clean = raw.map(Number).filter((n) => Number.isFinite(n) && n > 0);

      if (clean.length) {
        localStorage.setItem("last_payment_enrollment_ids", clean.join(","));
        return clean;
      }
    } catch {
      // ignore and try next
    }
  }

  return [];
}

/* ---------------- Component ---------------- */
const PaymentResult = () => {
  const query = useQuery();
  const navigate = useNavigate();

  const [status, setStatus] = useState("loading"); // loading | success | failed
  const [errorMsg, setErrorMsg] = useState("");

  useEffect(() => {
    let alive = true;

    (async () => {
      const ok = (query.get("ok") || "").trim(); // "1" یا "0"
      const pid = (query.get("pid") || "").trim(); // PaymentIntent public_id
      const ref = (query.get("ref") || "").trim(); // ref بانک
      const tc = (query.get("tc") || "").trim(); // tracking code اگر داشتی
      const token = (query.get("token") || "").trim(); // توکن بانک اگر داشتی
      const flow = (query.get("flow") || "").trim();

      // ids ممکنه با چند نام مختلف بیاد (بک‌اند شما enrollment_ids می‌فرسته)
      const idsFromUrl =
        (query.get("ids") ||
          query.get("enrollment_ids") ||
          query.get("enrollmentIds") ||
          query.get("enrollments") ||
          "").trim();

      // enrollment تکی ممکنه با چند نام مختلف بیاد
      const enrollmentIdSingle =
        (query.get("enrollment_id") ||
          query.get("enrollment") ||
          query.get("enroll") ||
          query.get("eid") ||
          "").trim();

      const kind = pickKind({ flow, queryKind: query.get("kind") });

      // پرداخت ناموفق
      if (ok !== "1") {
        if (!alive) return;
        setStatus("failed");
        setErrorMsg("پرداخت ناموفق بود یا لغو شد.");
        return;
      }

      if (!alive) return;
      setStatus("success");

      // ✅ 1) اگر enrollment_id تکی داریم → برو کارت تکی
      if (enrollmentIdSingle) {
        const params = new URLSearchParams();
        params.set("ok", "1");
        params.set("kind", kind);
        if (pid) params.set("pid", pid);
        if (ref) params.set("ref", ref);
        if (tc) params.set("tc", tc);
        if (token) params.set("token", token);
        if (flow) params.set("flow", flow);

        const dashRole =
          (query.get("role") || "").toLowerCase().trim() ||
          pickDashboardRoleForFlow(flow);

        navigate(
          `/dashboard/${encodeURIComponent(dashRole)}/enrollments/${encodeURIComponent(
            enrollmentIdSingle
          )}/card?${params.toString()}`,
          { replace: true }
        );
        return;
      }

      // ✅ 2) اگر ids/enrollment_ids داریم → برو bulk cards
      let idsStr = idsFromUrl;

      // گاهی بک‌اند یک عدد می‌فرسته؛ ما یکسان‌سازی می‌کنیم
      if (idsStr) {
        const parsed = parseIds(idsStr);
        idsStr = parsed.length ? parsed.join(",") : "";
      }

      // ✅ 3) اگر ids نداریم ولی pid داریم، از بک‌اند resolve کن
      if (!idsStr && pid) {
        const resolved = await resolveEnrollmentIdsByPid(pid, kind);
        if (resolved.length) idsStr = resolved.join(",");
      }

      // اگر به ids رسیدیم → برو صفحه چاپ کارت‌ها
      if (idsStr) {
        const params = new URLSearchParams();
        params.set("ids", idsStr);
        params.set("kind", kind);
        params.set("ok", "1");

        if (pid) params.set("pid", pid);
        if (ref) params.set("ref", ref);
        if (tc) params.set("tc", tc);
        if (token) params.set("token", token);
        if (flow) params.set("flow", flow);

        const dashRole =
          (query.get("role") || "").toLowerCase().trim() ||
          pickDashboardRoleForFlow(flow || "bulk_after_payment");

        // ✅ این مسیر با App.js شما match می‌شود
        navigate(
          `/dashboard/${encodeURIComponent(dashRole)}/enrollments/bulk?${params.toString()}`,
          { replace: true }
        );
        return;
      }

      // ✅ اگر هیچ چیز نداشتیم، حداقل با pid برگرد داشبورد
      const dashRole =
        (query.get("role") || "").toLowerCase().trim() ||
        pickDashboardRoleForFlow(flow);

      navigate(
        `/dashboard/${encodeURIComponent(dashRole)}?ok=1${pid ? `&pid=${encodeURIComponent(pid)}` : ""}${
          ref ? `&ref=${encodeURIComponent(ref)}` : ""
        }`,
        { replace: true }
      );
    })();

    return () => {
      alive = false;
    };
  }, [query, navigate]);

  /* ---------------- UI ---------------- */
  if (status === "loading") {
    return (
      <div className="flex items-center justify-center h-full">
        <h2>در حال پردازش نتیجه پرداخت...</h2>
      </div>
    );
  }

  if (status === "failed") {
    return (
      <div className="flex flex-col items-center justify-center h-full">
        <h2 className="text-red-600 font-bold mb-3">
          {errorMsg || "پرداخت ناموفق بود یا لغو شد."}
        </h2>
        <button
          onClick={() => navigate("/dashboard", { replace: true })}
          className="px-4 py-2 rounded bg-red-500 text-white"
        >
          بازگشت به داشبورد
        </button>
      </div>
    );
  }

  return (
    <div className="flex items-center justify-center h-full">
      <h2 className="text-green-600 font-bold">
        پرداخت با موفقیت انجام شد، در حال انتقال...
      </h2>
    </div>
  );
};

export default PaymentResult;
