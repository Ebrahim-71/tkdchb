import React, { useEffect, useState } from "react";
import axios from "axios";
import PaginatedList from "../../../common/PaginatedList";
import DatePicker from "react-multi-date-picker";
import persian from "react-date-object/calendars/persian";
import persian_fa from "react-date-object/locales/persian_fa";
import "./HeyatCoachesTable.css";

const HeyatCoachesTable = () => {
  const [coaches, setCoaches] = useState([]);
  const [dropdownList, setDropdownList] = useState({
    clubs: [],
    belts: [],
    nationalDegrees: [],
    internationalDegrees: []
  });
  const [filters, setFilters] = useState({
    club: "همه",
    belt: "همه",
    nationalLevel: "همه",
    internationalLevel: "همه",
    birthFrom: "",
    birthTo: "",
    search: ""
  });

  const token = localStorage.getItem("heyat_token");

  const fetchDropdownOptions = async () => {
    try {
      const res = await axios.get("https://api.chbtkd.ir/api/auth/heyat/form-data/", {
        headers: { Authorization: `Bearer ${token}` }
      });

      const clubs = res.data.clubs.map((c) => ({
        label: c.club_name,
        value: c.club_name
      }));

      const beltGrades = [
        "مشکی دان 1", "مشکی دان 2", "مشکی دان 3", "مشکی دان 4",
        "مشکی دان 5", "مشکی دان 6", "مشکی دان 7", "مشکی دان 8",
        "مشکی دان 9", "مشکی دان 10"
      ];

      const degrees = ["درجه بین‌الملل ندارد", "درجه یک", "درجه دو", "درجه سه", "ممتاز"];

      setDropdownList({
        clubs: [{ label: "باشگاه‌ها", value: "همه" }, ...clubs],
        belts: [{ label: "کمربندها", value: "همه" }, ...beltGrades.map(b => ({ label: b, value: b }))],
        nationalDegrees: [{ label: "درجات ملی", value: "همه" }, ...degrees.map(d => ({ label: d, value: d }))],
        internationalDegrees: [{ label: "درجات بین‌المللی", value: "همه" }, ...degrees.map(d => ({ label: d, value: d }))]
      });
    } catch (err) {
      console.error("خطا در دریافت گزینه‌های فیلتر", err);
    }
  };

  const fetchCoaches = async () => {
    try {
      const params = {};
      if (filters.club !== "همه") params.club = filters.club;
      if (filters.belt !== "همه") params.belt = filters.belt;
      if (filters.nationalLevel !== "همه") params.national_level = filters.nationalLevel;
      if (filters.internationalLevel !== "همه") params.international_level = filters.internationalLevel;
      if (filters.birthFrom) params.birth_from = filters.birthFrom;
      if (filters.birthTo) params.birth_to = filters.birthTo;
      if (filters.search) params.search = filters.search;

      const res = await axios.get("https://api.chbtkd.ir/api/auth/heyat/coaches/", {
        headers: { Authorization: `Bearer ${token}` },
        params
      });

      setCoaches(res.data);
    } catch (err) {
      console.error("خطا در دریافت لیست مربی‌ها", err);
    }
  };

  useEffect(() => {
    fetchDropdownOptions();
  }, []);

  useEffect(() => {
    const delayDebounce = setTimeout(() => {
      fetchCoaches();
    }, 400);
    return () => clearTimeout(delayDebounce);
  }, [filters]);

  return (
    <div className="heyat-coaches-table">
      <h2 className="heyat-coaches-title">لیست مربی‌های هیئت</h2>

      <div className="heyat-coaches-filters">
        <select value={filters.club} onChange={(e) => setFilters((prev) => ({ ...prev, club: e.target.value }))}>
          {dropdownList.clubs.map((club) => (
            <option key={club.value} value={club.value}>{club.label}</option>
          ))}
        </select>

        <select value={filters.belt} onChange={(e) => setFilters((prev) => ({ ...prev, belt: e.target.value }))}>
          {dropdownList.belts.map((belt) => (
            <option key={belt.value} value={belt.value}>{belt.label}</option>
          ))}
        </select>

        <select value={filters.nationalLevel} onChange={(e) => setFilters((prev) => ({ ...prev, nationalLevel: e.target.value }))}>
          {dropdownList.nationalDegrees.map((d) => (
            <option key={d.value} value={d.value}>{d.label}</option>
          ))}
        </select>

        <select value={filters.internationalLevel} onChange={(e) => setFilters((prev) => ({ ...prev, internationalLevel: e.target.value }))}>
          {dropdownList.internationalDegrees.map((d) => (
            <option key={d.value} value={d.value}>{d.label}</option>
          ))}
        </select>

        <DatePicker
          calendar={persian}
          locale={persian_fa}
          value={filters.birthFrom}
          onChange={(date) => setFilters((prev) => ({ ...prev, birthFrom: date?.format("YYYY/MM/DD") }))}
          inputClass="date-input"
          placeholder="تاریخ تولد از"
        />

        <DatePicker
          calendar={persian}
          locale={persian_fa}
          value={filters.birthTo}
          onChange={(date) => setFilters((prev) => ({ ...prev, birthTo: date?.format("YYYY/MM/DD") }))}
          inputClass="date-input"
          placeholder="تاریخ تولد تا"
        />

        <input
          type="text"
          className="search-input"
          placeholder="جستجو بر اساس نام یا کد ملی"
          value={filters.search}
          onChange={(e) => setFilters((prev) => ({ ...prev, search: e.target.value }))}
        />
      </div>

      <div className="heyat-coaches-table-container">
        <div className="heyat-coaches-table-header">
          <div>نام و نام خانوادگی</div>
          <div>کد ملی</div>
          <div>تاریخ تولد</div>
          <div>درجه کمربند</div>
          <div>درجه ملی</div>
          <div>درجه بین‌المللی</div>
          <div>باشگاه‌ها</div>
        </div>

        <PaginatedList
          items={coaches}
          itemsPerPage={10}
          renderItem={(c, i) => (
            <div
              key={c.national_code}
              className={`heyat-coaches-table-row ${i % 2 === 0 ? "row-light" : "row-dark"}`}
            >
              <div data-label="نام و نام خانوادگی">{c.full_name}</div>
              <div data-label="کد ملی">{c.national_code}</div>
              <div data-label="تاریخ تولد">{c.birth_date}</div>
              <div data-label="درجه کمربند">{c.belt_grade}</div>
              <div data-label="درجه ملی">{c.national_certificate_date || "درجه ملی ندارد"}</div>
              <div data-label="درجه بین‌المللی">{c.international_certificate_date || "درجه بین‌الملل ندارد"}</div>
              <div data-label="باشگاه‌ها">{c.clubs?.join(" - ")}</div>
            </div>
          )}
        />
      </div>
    </div>
  );
};

export default HeyatCoachesTable;
