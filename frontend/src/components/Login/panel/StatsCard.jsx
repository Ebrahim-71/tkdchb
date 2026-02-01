import React, { useEffect, useState, useRef } from "react";
import axios from "axios";
import { useNavigate } from "react-router-dom";
import "./dashboard.css";

const API_BASE = "https://api.chbtkd.ir";

const StatsCard = () => {
  const [stats, setStats] = useState(null);
  const [error, setError] = useState("");
  const scrollRef = useRef(null);
  const navigate = useNavigate();
  const [canScrollLeft, setCanScrollLeft] = useState(false);
  const [canScrollRight, setCanScrollRight] = useState(true);

  useEffect(() => {
    const role = localStorage.getItem("user_role");
    const token = localStorage.getItem(`${role}_token`);

    if (!role || !token) {
      setError("توکن یا نقش یافت نشد.");
      return;
    }

    axios
      .get(`${API_BASE}/api/auth/dashboard/${role}/`, {
        headers: { Authorization: `Bearer ${token}` },
      })
      .then((res) => setStats(res.data))
      .catch((err) => {
        if (err.response?.status === 401) {
          localStorage.clear();
          navigate("/");
        } else {
          setError("دریافت اطلاعات ناموفق بود.");
        }
      });
  }, [navigate]);

  const updateScrollButtons = () => {
    const el = scrollRef.current;
    if (el) {
      setCanScrollLeft(el.scrollLeft > 0);
      setCanScrollRight(el.scrollLeft + el.clientWidth < el.scrollWidth - 5);
    }
  };

  const scroll = (offset) => {
    scrollRef.current.scrollBy({ left: offset, behavior: "smooth" });
  };

  useEffect(() => {
    const el = scrollRef.current;
    if (el) {
      el.addEventListener("scroll", updateScrollButtons);
      updateScrollButtons();
    }
    return () => {
      if (el) el.removeEventListener("scroll", updateScrollButtons);
    };
  }, [stats]);

  if (error) return <p className="error-text">{error}</p>;
  if (!stats) return <p className="loading-text">در حال بارگذاری...</p>;

  const staticCards = [];

  if (stats.role === "heyat") {
    staticCards.push(
      { title: "بازیکن", emoji: "👥", value: stats.student_count, bg: "#f3e5f5" },
      { title: "مربی", emoji: "👨‍🏫", value: stats.coach_count, bg: "#e8f5e9" },
      { title: "داور", emoji: "🧑‍⚖️", value: stats.referee_count, bg: "#fbe9e7" },
      { title: "باشگاه‌ها", emoji: "🏟️", value: stats.club_count, bg: "#e3f2fd" }
    );
  }

  if (stats.role === "club") {
    staticCards.push(
      { title: "نام موسس", emoji: "👤", value: stats.founder_name, bg: "#fce4ec" },
      { title: "شاگردان", emoji: "👥", value: stats.student_count, bg: "#e1f5fe" },
      { title: "مربی‌ها", emoji: "👨‍🏫", value: stats.coach_count, bg: "#ffe0b2" }
    );
  }

  if (["player", "coach", "referee", "both"].includes(stats.role)) {
    staticCards.push(
      { title: "مربی", emoji: "👨‍🏫", value: stats.coach_name, bg: "#fce4ec" },
      { title: "کمربند", emoji: "🥋", value: stats.belt_grade, bg: "#ede7f6" }
    );

    if (["coach", "both"].includes(stats.role)) {
      staticCards.push(
        { title: "شاگردان", emoji: "👥", value: stats.student_count, bg: "#e1f5fe" },
        { title: "باشگاه‌ها", emoji: "🏟️", value: stats.coaching_clubs_count, bg: "#ffe0b2" }
      );
    }
  }

  const dynamicCards = [
    { title: " طلای استانی", emoji: "🥇", value: stats.gold_medals, bg: "#fff3e0" },
    { title: " نقره استانی", emoji: "🥈", value: stats.silver_medals, bg: "#eeeeee" },
    { title: " برنز استانی", emoji: "🥉", value: stats.bronze_medals, bg: "#efebe9" },
    { title: " طلای کشوری", emoji: "🥇", value: stats.gold_medals_country, bg: "#fff3e0" },
    { title: " نقره کشوری", emoji: "🥈", value: stats.silver_medals_country, bg: "#eeeeee" },
    { title: " برنز کشوری", emoji: "🥉", value: stats.bronze_medals_country, bg: "#efebe9" },
    { title: " طلای جهانی", emoji: "🥇", value: stats.gold_medals_int, bg: "#fff3e0" },
    { title: " نقره جهانی", emoji: "🥈", value: stats.silver_medals_int, bg: "#eeeeee" },
    { title: " برنز جهانی", emoji: "🥉", value: stats.bronze_medals_int, bg: "#efebe9" },
    { title: " امتیاز مسابقه", emoji: "🎯", value: stats.ranking_competition, bg: "#f3e5f5" },
    { title: " امتیاز کل", emoji: "🌟", value: stats.ranking_total, bg: "#e8eaf6" },
    { title: " مسابقات", emoji: "🎽", value: stats.match_count, bg: "#e0f2f1" },
    { title: " سمینارها", emoji: "🎓", value: stats.seminar_count, bg: "#fff8e1" },
  ];

  const filteredDynamic = dynamicCards.filter(
    (card) => card.value !== null && card.value !== undefined && Number(card.value) !== 0
  );

  const cardsToShow = [...staticCards, ...filteredDynamic];

  return (
    <div className="stats-section">
      <div
        className="scroll-btn fixed left"
        onClick={() => scroll(-200)}
        style={{ opacity: canScrollLeft ? 1 : 0.4 }}
      >
        ❯
      </div>
      <div className="stats-carousel" ref={scrollRef}>
        {cardsToShow.map((card, index) => (
          <div key={index} className="carousel-card" style={{ backgroundColor: card.bg }}>
            <div className="emoji">{card.emoji || ""}</div>
            <div className="title">{card.title}</div>
            <div className="value">{card.value}</div>
          </div>
        ))}
      </div>
      <div
        className="scroll-btn fixed right"
        onClick={() => scroll(200)}
        style={{ opacity: canScrollRight ? 1 : 0.4 }}
      >
        ❮
      </div>
    </div>
  );
};

export default StatsCard;
