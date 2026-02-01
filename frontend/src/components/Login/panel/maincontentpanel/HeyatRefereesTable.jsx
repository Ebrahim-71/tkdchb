import React, { useEffect, useState } from "react";
import axios from "axios";
import PaginatedList from "../../../common/PaginatedList";
import DatePicker from "react-multi-date-picker";
import persian from "react-date-object/calendars/persian";
import persian_fa from "react-date-object/locales/persian_fa";
import "./HeyatRefereesTable.css";

const refereeFields = ["کیوروگی", "پومسه", "هانمادانگ"];

const HeyatRefereesTable = () => {
  const [referees, setReferees] = useState([]);
  const [filters, setFilters] = useState({
    belt: "همه",
    nationalLevel: "همه",
    internationalLevel: "همه",
    refereeField: "همه",
    birthFrom: "",
    birthTo: "",
    search: ""
  });

  const [dropdownList, setDropdownList] = useState({
    belts: [],
    nationalDegrees: [],
    internationalDegrees: []
  });

  const token = localStorage.getItem("heyat_token");

  const fetchDropdownOptions = async () => {
    try {
      const res = await axios.get("https://api.chbtkd.ir/api/auth/heyat/form-data/", {
        headers: { Authorization: `Bearer ${token}` }
      });

      const beltGrades = [
        "مشکی دان 1", "مشکی دان 2", "مشکی دان 3", "مشکی دان 4",
        "مشکی دان 5", "مشکی دان 6", "مشکی دان 7", "مشکی دان 8",
        "مشکی دان 9", "مشکی دان 10"
      ];
      const degrees = ["درجه یک", "درجه دو", "درجه سه", "ممتاز"];

      setDropdownList({
        belts: [{ label: "کمربندها", value: "همه" }, ...beltGrades.map(b => ({ label: b, value: b }))],
        nationalDegrees: [{ label: "درجات ملی", value: "همه" }, ...degrees.map(d => ({ label: d, value: d }))],
        internationalDegrees: [{ label: "درجات بین‌المللی", value: "همه" }, ...degrees.map(d => ({ label: d, value: d }))],
      });
    } catch (err) {
      console.error("خطا در دریافت گزینه‌های فیلتر", err);
    }
  };

  const fetchReferees = async () => {
    try {
      const params = {};
      if (filters.belt !== "همه") params.belt = filters.belt;
      if (filters.nationalLevel !== "همه") params.national_level = filters.nationalLevel;
      if (filters.internationalLevel !== "همه") params.international_level = filters.internationalLevel;
      if (filters.refereeField !== "همه") params.referee_field = filters.refereeField;
      if (filters.birthFrom) params.birth_from = filters.birthFrom;
      if (filters.birthTo) params.birth_to = filters.birthTo;
      if (filters.search) params.search = filters.search;

      const res = await axios.get("https://api.chbtkd.ir/api/auth/heyat/referees/", {
        headers: { Authorization: `Bearer ${token}` },
        params
      });

      setReferees(res.data);
    } catch (err) {
      console.error("خطا در دریافت لیست داوران", err);
    }
  };

  useEffect(() => {
    fetchDropdownOptions();
  }, []);

  useEffect(() => {
    const debounce = setTimeout(() => {
      fetchReferees();
    }, 400);
    return () => clearTimeout(debounce);
  }, [filters]);

  return (
    <div className="heyat-referees-table">
      <h2 className="heyat-referees-title">لیست داوران هیئت</h2>

      <div className="heyat-referees-filters">
        <select value={filters.belt} onChange={(e) => setFilters(prev => ({ ...prev, belt: e.target.value }))}>
          {dropdownList.belts.map((belt) => (
            <option key={belt.value} value={belt.value}>{belt.label}</option>
          ))}
        </select>

        <select value={filters.nationalLevel} onChange={(e) => setFilters(prev => ({ ...prev, nationalLevel: e.target.value }))}>
          {dropdownList.nationalDegrees.map((d) => (
            <option key={d.value} value={d.value}>{d.label}</option>
          ))}
        </select>

        <select value={filters.internationalLevel} onChange={(e) => setFilters(prev => ({ ...prev, internationalLevel: e.target.value }))}>
          {dropdownList.internationalDegrees.map((d) => (
            <option key={d.value} value={d.value}>{d.label}</option>
          ))}
        </select>

        <select value={filters.refereeField} onChange={(e) => setFilters(prev => ({ ...prev, refereeField: e.target.value }))}>
          {["همه", ...refereeFields].map((f) => (
            <option key={f} value={f}>{f}</option>
          ))}
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

      <div className="heyat-referees-table-container">
        <div className="heyat-referees-table-header columns-14">
          <div>نام و نام خانوادگی</div>
          <div>کد ملی</div>
          <div>تاریخ تولد</div>
          <div>درجه کمربند</div>

          {refereeFields.map((f) => (
            <React.Fragment key={f}>
              <div>{f}</div>
              <div>ملی {f}</div>
              <div>بین‌الملل {f}</div>
            </React.Fragment>
          ))}
        </div>

        <PaginatedList
          items={referees}
          itemsPerPage={10}
          renderItem={(r, i) => (
            <div
              key={r.national_code}
              className={`heyat-referees-table-row columns-14 ${i % 2 === 0 ? "row-light" : "row-dark"}`}
            >
              <div data-label="نام و نام خانوادگی">{r.full_name}</div>
              <div data-label="کد ملی">{r.national_code}</div>
              <div data-label="تاریخ تولد">{r.birth_date}</div>
              <div data-label="درجه کمربند">{r.belt_grade}</div>

              {refereeFields.map((field) => {
                const data = r.referee_fields?.[field];
                return (
                  <React.Fragment key={field}>
                    <div data-label={field}>{data?.active ? "✅" : "❌"}</div>
                    <div data-label={`ملی ${field}`}>{data?.national || "درجه ملی ندارد"}</div>
                    <div data-label={`بین‌الملل ${field}`}>{data?.international || "درجه بین‌الملل ندارد"}</div>
                  </React.Fragment>
                );
              })}
            </div>
          )}
        />
      </div>
    </div>
  );
};

export default HeyatRefereesTable;
