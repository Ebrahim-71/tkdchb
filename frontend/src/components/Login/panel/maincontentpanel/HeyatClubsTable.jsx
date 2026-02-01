import React, { useEffect, useState } from "react";
import axios from "axios";
import PaginatedList from "../../../common/PaginatedList";
import "./HeyatClubsTable.css";

const HeyatClubsTable = () => {
  const [clubs, setClubs] = useState([]);
  const [search, setSearch] = useState("");
  const [error, setError] = useState(null);

  const token = localStorage.getItem("heyat_token");

  const fetchClubs = async () => {
    if (!token) {
      setError("توکن یافت نشد. لطفاً وارد شوید.");
      return;
    }

    try {
      const res = await axios.get("https://api.chbtkd.ir/api/auth/heyat/clubs/", {
        headers: { Authorization: `Bearer ${token}` },
        params: search ? { search } : {},
      });
      setClubs(res.data);
      setError(null);
    } catch (err) {
      console.error("خطا در دریافت لیست باشگاه‌ها", err);
      setError("خطا در دریافت لیست باشگاه‌ها");
    }
  };

  useEffect(() => {
    const delay = setTimeout(() => {
      fetchClubs();
    }, 300);
    return () => clearTimeout(delay);
  }, [search]);

  return (
    <div className="heyat-clubs-table">
      <h2 className="heyat-clubs-title">لیست باشگاه‌های هیئت</h2>

      <div className="heyat-clubs-filters">
        <input
          type="text"
          className="search-input"
          placeholder="جستجو بر اساس نام یا مدیر باشگاه"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
      </div>

      {error && <div className="error-message">{error}</div>}

      <div className="heyat-clubs-table-container">
        <div className="heyat-clubs-table-header columns-6">
          <div>نام باشگاه</div>
          <div>مدیر</div>
          <div>موبایل باشگاه</div>
          <div>موبایل مدیر</div>
          <div>تعداد شاگرد</div>
          <div>تعداد مربی</div>
        </div>

        <PaginatedList
          items={clubs}
          itemsPerPage={10}
          renderItem={(club, i) => (
            <div
              key={club.id || i}
              className={`heyat-clubs-table-row columns-6 ${i % 2 === 0 ? "row-light" : "row-dark"}`}
            >
              <div data-label="نام باشگاه">{club.club_name}</div>
              <div data-label="مدیر">{club.manager_name}</div>
              <div data-label="موبایل باشگاه">{club.phone}</div>
              <div data-label="موبایل مدیر">{club.manager_phone}</div>
              <div data-label="تعداد شاگرد">{club.student_count}</div>
              <div data-label="تعداد مربی">{club.coach_count}</div>
            </div>
          )}
        />
      </div>
    </div>
  );
};

export default HeyatClubsTable;
