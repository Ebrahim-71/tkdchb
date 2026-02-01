import React, { useEffect, useState } from "react";
import axios from "axios";
import PaginatedList from "../../../common/PaginatedList";
import DatePicker from "react-multi-date-picker";
import persian from "react-date-object/calendars/persian";
import persian_fa from "react-date-object/locales/persian_fa";
import "./StudentsTable.css";

const beltGrades = [
  "همه", "سفید", "زرد", "سبز", "آبی", "قرمز",
  "مشکی دان 1", "مشکی دان 2", "مشکی دان 3", "مشکی دان 4",
  "مشکی دان 5", "مشکی دان 6", "مشکی دان 7", "مشکی دان 8",
  "مشکی دان 9", "مشکی دان 10"
];

const StudentsTable = () => {
  const [students, setStudents] = useState([]);
  const [dropdownList, setDropdownList] = useState({ coaches: [], clubs: [] });
  const [filters, setFilters] = useState({
    coach: "همه",
    club: "همه",
    belt: "همه",
    birthFrom: "",
    birthTo: "",
    search: ""
  });

  const role = localStorage.getItem("user_role");
  const token = localStorage.getItem(`${role}_token`);
  const isClub = role === "club";
  const isCoach = role === "coach" || role === "both";
  const isHeyat = role === "heyat";

  // تعداد ستون‌های فعلی + 3 ستون جدید (مسابقات، مدال‌ها، رنکینگ)
  const baseCols = isHeyat ? 7 : 6;
  const columnCount = baseCols + 3;

  useEffect(() => {
    const fetchOptions = async () => {
      try {
        let url = "";
        if (isClub) url = "https://api.chbtkd.ir/api/auth/club/coaches/";
        else if (isCoach) url = "https://api.chbtkd.ir/api/auth/coach/clubs/";
        else if (isHeyat) url = "https://api.chbtkd.ir/api/auth/heyat/form-data/";

        const res = await axios.get(url, {
          headers: { Authorization: `Bearer ${token}` },
        });

        if (isHeyat) {
          setDropdownList({
            coaches: ["همه", ...res.data.coaches.map(c => c.name)],
            clubs: ["همه", ...res.data.clubs.map(c => c.club_name)],
          });
        } else {
          const items = res.data.map(item => (isClub ? item.name : item.club_name));
          setDropdownList({
            coaches: ["همه", ...items],
            clubs: []
          });
        }
      } catch (err) {
        console.error("خطا در دریافت فیلترها", err);
      }
    };
    fetchOptions();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const fetchData = async () => {
      try {
        const params = {};
        if (isHeyat) {
          if (filters.coach !== "همه") params.coach = filters.coach;
          if (filters.club !== "همه") params.club = filters.club;
        } else {
          if (filters.coach !== "همه") {
            if (isClub) params.coach = filters.coach;
            if (isCoach) params.club = filters.coach;
          }
        }
        if (filters.belt !== "همه") params.belt = filters.belt;
        if (filters.birthFrom) params.birth_from = filters.birthFrom;
        if (filters.birthTo) params.birth_to = filters.birthTo;
        if (filters.search) params.search = filters.search;

        const url = isClub
          ? "https://api.chbtkd.ir/api/auth/club/students/"
          : isCoach
          ? "https://api.chbtkd.ir/api/auth/coach/students/"
          : "https://api.chbtkd.ir/api/auth/heyat/students/";

        const res = await axios.get(url, {
          headers: { Authorization: `Bearer ${token}` },
          params,
        });

        setStudents(res.data || []);
      } catch (err) {
        console.error("خطا در دریافت شاگردان", err);
      }
    };

    const delay = setTimeout(fetchData, 400);
    return () => clearTimeout(delay);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filters]);

  const renderMedals = (s) => {
    const g = s?.gold_medals ?? 0;
    const sil = s?.silver_medals ?? 0;
    const b = s?.bronze_medals ?? 0;
    return (
      <div className="medal-badges" title={`طلا: ${g} | نقره: ${sil} | برنز: ${b}`}>
        <span className="badge badge-gold">ط {g}</span>
        <span className="badge badge-silver">ن {sil}</span>
        <span className="badge badge-bronze">ب {b}</span>
      </div>
    );
  };

  return (
    <div className="students-table">
      <h2 className="students-title">لیست شاگردان</h2>

      <div className="students-filters">
        {isHeyat ? (
          <>
            <select value={filters.coach} onChange={(e) => setFilters(prev => ({ ...prev, coach: e.target.value }))}>
              {dropdownList.coaches.map((c) => <option key={c} value={c}>{c}</option>)}
            </select>
            <select value={filters.club} onChange={(e) => setFilters(prev => ({ ...prev, club: e.target.value }))}>
              {dropdownList.clubs.map((c) => <option key={c} value={c}>{c}</option>)}
            </select>
          </>
        ) : (
          <select value={filters.coach} onChange={(e) => setFilters(prev => ({ ...prev, coach: e.target.value }))}>
            {dropdownList.coaches.map((c) => <option key={c} value={c}>{c}</option>)}
          </select>
        )}

        <select value={filters.belt} onChange={(e) => setFilters(prev => ({ ...prev, belt: e.target.value }))}>
          {beltGrades.map((belt) => <option key={belt} value={belt}>{belt}</option>)}
        </select>

        <DatePicker
          calendar={persian}
          locale={persian_fa}
          value={filters.birthFrom}
          onChange={(date) => setFilters(prev => ({ ...prev, birthFrom: date?.format("YYYY/MM/DD") }))}
          inputClass="date-input"
          placeholder="تاریخ تولد از"
        />
        <DatePicker
          calendar={persian}
          locale={persian_fa}
          value={filters.birthTo}
          onChange={(date) => setFilters(prev => ({ ...prev, birthTo: date?.format("YYYY/MM/DD") }))}
          inputClass="date-input"
          placeholder="تاریخ تولد تا"
        />

        <input
          type="text"
          className="search-input"
          placeholder="جستجو بر اساس نام یا کد ملی"
          value={filters.search}
          onChange={(e) => setFilters(prev => ({ ...prev, search: e.target.value }))}
        />
      </div>

      <div className="students-table-container">
        <div className={`students-table-header columns-${columnCount}`}>
          <div>نام و نام خانوادگی</div>
          <div>کد ملی</div>
          <div>تاریخ تولد</div>
          <div>درجه کمربند</div>
          <div>تاریخ اخذ کمربند</div>

          {/* ستون‌های جدید */}
          <div>مسابقات</div>
          <div>مدال‌ها</div>
          <div>رنکینگ</div>

          {isHeyat ? (
            <>
              <div>باشگاه</div>
              <div>مربی</div>
            </>
          ) : (
            <div>{isClub ? "مربی" : "باشگاه"}</div>
          )}
        </div>

        <PaginatedList
          items={students}
          itemsPerPage={10}
          renderItem={(s, i) => (
            <div
              key={s.national_code || i}
              className={`students-table-row columns-${columnCount} ${i % 2 === 0 ? "row-light" : "row-dark"}`}
            >
              <div data-label="نام و نام خانوادگی">{s.full_name}</div>
              <div data-label="کد ملی">{s.national_code}</div>
              <div data-label="تاریخ تولد">{s.birth_date}</div>
              <div data-label="درجه کمربند">{s.belt_grade}</div>
              <div data-label="تاریخ اخذ کمربند">{s.belt_certificate_date}</div>

              {/* ستون‌های جدید */}
              <div data-label="مسابقات">{s.competitions_count ?? 0}</div>
              <div data-label="مدال‌ها">{renderMedals(s)}</div>
              <div data-label="رنکینگ">{s.ranking_total ?? s.ranking_competition ?? 0}</div>

              {isHeyat ? (
                <>
                  <div data-label="باشگاه">{s.club}</div>
                  <div data-label="مربی">{s.coach_name}</div>
                </>
              ) : (
                <div data-label={isClub ? "مربی" : "باشگاه"}>{isClub ? s.coach_name : s.club}</div>
              )}
            </div>
          )}
        />
      </div>
    </div>
  );
};

export default StudentsTable;
