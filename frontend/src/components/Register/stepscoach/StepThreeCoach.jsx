import React, { useEffect, useState } from "react";
import axios from "axios";
import DatePicker from "react-multi-date-picker";
import persian from "react-date-object/calendars/persian";
import persian_fa from "react-date-object/locales/persian_fa";
import "./CoachRegister.css";

const StepThreeCoach = ({ data, onDataChange, onNext, onBack }) => {
  const [clubs, setClubs] = useState([]);
  const [coaches, setCoaches] = useState([]);
  const [heyats, setHeyats] = useState([]);
  const [errors, setErrors] = useState({});
  const [dropdownOpen, setDropdownOpen] = useState(false);
  const [showErrorModal, setShowErrorModal] = useState(false);
  const [modalErrorText, setModalErrorText] = useState("");

  useEffect(() => {
    if (!data.gender) return;

    axios
      .get(`https://api.chbtkd.ir/api/auth/form-data/?gender=${data.gender}`)
      .then((res) => {
        setHeyats(res.data.heyats || []);
        setClubs(res.data.clubs || []);
        setCoaches(res.data.coaches || []);
      })
      .catch((err) => {
        console.error("Form data fetch error:", err);
      });
  }, [data.gender]);

  const toggleDropdown = () => setDropdownOpen((prev) => !prev);

  const handleChange = (e) => {
    const { name, value } = e.target;

    if (name === "coach") {
      const selectedCoach = coaches.find((c) => c.id.toString() === value);
      onDataChange({
        coach: value,
        coachFullName: selectedCoach ? selectedCoach.full_name : "",
      });
    } else {
      onDataChange({ [name]: value });
    }
  };
  
  const handleRoleChange = (e) => {
    const role = e.target.value;
    let isCoach = false;
    let isReferee = false;

    if (role === 'coach') isCoach = true;
    else if (role === 'referee') isReferee = true;
    else if (role === 'both') {
      isCoach = true;
      isReferee = true;
    }

    onDataChange({
      role,
      is_coach: isCoach,
      is_referee: isReferee,
    });
  };

  const handleClubCheck = (e) => {
    const { value, checked } = e.target;
    const clubId = parseInt(value, 10);
    let updated = data.selectedClubs || [];

    if (checked) {
      if (!updated.includes(clubId) && updated.length < 3) {
        updated.push(clubId);
      }
    } else {
      updated = updated.filter((id) => id !== clubId);
    }

    onDataChange({ selectedClubs: updated });
  };

  const validate = () => {
    const newErrors = {};

    if (!data.role) newErrors.role = "نقش را انتخاب کنید";
    if ((data.selectedClubs || []).length < 1) newErrors.selectedClubs = "حداقل یک باشگاه انتخاب کنید";
    if (!data.coach && data.coach !== "other") newErrors.coach = "مربی را انتخاب کنید";
    if (data.coach === "other" && !data.customCoachName) newErrors.customCoachName = "نام مربی را وارد کنید";
    if (!data.belt_grade) newErrors.belt_grade = "درجه کمربند را انتخاب کنید";
    if (!/^[\d/]+$/.test(data.belt_certificate_number || "")) newErrors.belt_certificate_number = "شماره حکم فقط شامل عدد و / باشد";
    if (!data.belt_certificate_date) newErrors.belt_certificate_date = "تاریخ حکم را وارد کنید";

    setErrors(newErrors);

    if (Object.keys(newErrors).length > 0) {
      const firstError = Object.values(newErrors)[0];
      setModalErrorText(firstError);
      setShowErrorModal(true);
      return false;
    }

    return true;
  };

  const handleNext = () => {
    if (validate()) onNext();
  };

  return (
    <div className="step">
      <h2>اطلاعات تکواندو</h2>

      <label>نقش
        <select
          name="role"
          value={data.role || ""}
          onChange={handleRoleChange}  // اینجا به جای handleChange بذار
          className={errors.role ? "invalid" : ""}
          style={{ width: '104%' }}
        >
          <option value="">انتخاب کنید</option>
          <option value="coach">مربی هستم</option>
          <option value="referee">داور هستم</option>
          <option value="both">هم مربی هم داور هستم</option>
    </select>
      </label>

      <label>هیئت
        <select name="tkd_board" value={data.tkd_board || ''} onChange={handleChange}  style={{ width: '104%' }}>
          <option value="">انتخاب کنید</option>
          {heyats.map(h => (
            <option key={h.id} value={h.id}>{h.name}</option> 
          ))}
        </select>
      </label>


      <div className="custom-select-checkbox">
        <label>باشگاه‌ها</label>
        <div className="dropdown" onClick={toggleDropdown} style={{ width: '100%' }}>
          <button type="button" className="dropdown-toggle">
            {data.selectedClubs?.length ? `${data.selectedClubs.length} انتخاب شده` : 'انتخاب کنید'}
      
          </button>
          {dropdownOpen && (
            <div className="dropdown-menu">
              {clubs.map((club) => (
                <label key={club.id} className="dropdown-item">
                  <input
                    type="checkbox"
                    value={club.id}
                    checked={data.selectedClubs?.includes(club.id)}
                    onChange={handleClubCheck}
                    onClick={(e) => e.stopPropagation()}
                  />
                  {club.club_name}
                </label>
              ))}
            </div>
          )}
        </div>
      </div>

      <label>مربی
        <select name="coach" value={data.coach || ""} onChange={handleChange} className={errors.coach ? "invalid" : ""}style={{ width: '104%' }}>
     
          <option value="">انتخاب کنید</option>
          {coaches.map((c) => (
            <option key={c.id} value={c.id}>{c.full_name}</option>
          ))}
          <option value="other">مربی دیگر</option>
        </select>
      </label>

      {data.coach === "other" && (
        <label>نام مربی
          <input
            type="text"
            name="customCoachName"
            value={data.customCoachName || ""}
            onChange={handleChange}
            className={errors.customCoachName ? "invalid" : ""}
          />
        </label>
      )}

      <label>درجه کمربند
        <select name="belt_grade" value={data.belt_grade || ""} onChange={handleChange} className={errors.belt_grade ? "invalid" : ""}style={{ width: '104%' }}>
          
          <option value="">انتخاب کنید</option>
          {[...Array(10)].map((_, i) => (
            <option key={i} value={`مشکی دان ${i + 1}`}>{`مشکی دان ${i + 1}`}</option>
          ))}
        </select>
      </label>

      <label>شماره حکم
        <input
          name="belt_certificate_number"
          value={data.belt_certificate_number || ""}
          onChange={handleChange}
          className={errors.belt_certificate_number ? "invalid" : ""}
        />
      </label>

      <label className="birth-date">تاریخ اخذ کمربند
        <DatePicker
          calendar={persian}
          locale={persian_fa}
          maxDate={new Date()}
          value={data.belt_certificate_date || null}
          onChange={(date) => date && onDataChange({ belt_certificate_date: date.format("YYYY/MM/DD") })}
          format="YYYY/MM/DD"
          calendarPosition="bottom-right"
          placeholder="انتخاب کنید"
        />
      </label>

      <div className="step-buttons">
        <button type="button" onClick={onBack}>مرحله قبل</button>
        <button type="button" onClick={handleNext}>مرحله بعد</button>
      </div>

      {showErrorModal && (
        <div className="modal-error-overlay">
          <div className="modal-error-box">
            <p>{modalErrorText}</p>
            <button onClick={() => setShowErrorModal(false)}>باشه</button>
          </div>
        </div>
      )}
    </div>
  );
};

export default StepThreeCoach;
