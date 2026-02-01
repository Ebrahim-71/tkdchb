// src/components/seminar/SeminarsSection.jsx
import React, { useEffect, useState } from "react";
import axios from "axios";
import SeminarCard from "./SeminarCard";

const API_BASE = process.env.REACT_APP_API_BASE_URL || "https://api.chbtkd.ir";

const SeminarsSection = ({ role }) => {
  const safeRole = (role || localStorage.getItem("user_role") || "player").toLowerCase();

  const [items, setItems] = useState([]);
  const [show, setShow] = useState("upcoming"); // open | upcoming | past | all
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState("");

  const load = async (signal) => {
    setLoading(true);
    setErr("");
    try {
      const { data } = await axios.get(`${API_BASE}/api/competitions/seminars/sidebar/`, {
        params: { role: safeRole, show, limit: 12 },
        signal,
      });
      setItems(Array.isArray(data) ? data : []);
    } catch (e) {
      if (axios.isCancel?.(e) || e.name === "CanceledError") return;
      setErr("خطا در دریافت لیست سمینارها");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    const controller = new AbortController();
    load(controller.signal);
    return () => controller.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [safeRole, show]);

  const btnStyle = (active) => ({
    padding: "8px 12px",
    border: "1px solid #222",
    borderRadius: 8,
    background: active ? "rgb(141 157 255)" : "#fff",
    fontFamily: "IRANSansWeb",
    cursor: "pointer",
  });

  return (
    <div style={{ width: "100%" }}>
      <div style={{ display: "flex", gap: 8, margin: "15px 0 12px", flexWrap: "wrap" }}>
        <button
          type="button"
          aria-pressed={show === "open"}
          onClick={() => setShow("open")}
          style={btnStyle(show === "open")}
        >
          در حال ثبت‌نام
        </button>

        <button
          type="button"
          aria-pressed={show === "upcoming"}
          onClick={() => setShow("upcoming")}
          style={btnStyle(show === "upcoming")}
        >
          رویدادهای آینده
        </button>

        <button
          type="button"
          aria-pressed={show === "past"}
          onClick={() => setShow("past")}
          style={btnStyle(show === "past")}
        >
          گذشته
        </button>

        <button
          type="button"
          aria-pressed={show === "all"}
          onClick={() => setShow("all")}
          style={btnStyle(show === "all")}
        >
          همه
        </button>
      </div>

      {loading && <p>در حال بارگذاری…</p>}
      {err && <p style={{ color: "crimson" }}>{err}</p>}
      {!loading && !err && items.length === 0 && <p>موردی یافت نشد.</p>}

      <div
        style={{
          display: "grid",
          gap: 16,
          justifyItems: "center",
        }}
      >
        {items.map((s) => (
          <SeminarCard key={s.public_id} seminar={s} />
        ))}
      </div>
    </div>
  );
};

export default SeminarsSection;
