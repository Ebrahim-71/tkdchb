import React, { useEffect, useState } from "react";
import axios from "axios";
import DatePicker from "react-multi-date-picker";
import persian from "react-date-object/calendars/persian";
import persian_fa from "react-date-object/locales/persian_fa";
import "./PlayerRegister.css";

const StepThreePlayer = ({ data, onDataChange,onSubmit, onNext, onBack }) => {
  const [clubs, setClubs] = useState([]);
  const [coaches, setCoaches] = useState([]);
  const [heyats, setHeyats] = useState([]);
  const [beltChoices, setBeltChoices] = useState([]);
  const [errors, setErrors] = useState({});
  const [showErrorModal, setShowErrorModal] = useState(false);
  const [modalErrorText, setModalErrorText] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);



  useEffect(() => {
    if (!data.gender) return;

    axios.get(`https://api.chbtkd.ir/api/auth/form-data-player/?gender=${data.gender}`)
      .then((res) => {
        setHeyats(res.data.heyats || []);
        setClubs(res.data.clubs || []);
        setCoaches(res.data.coaches || []);
        setBeltChoices(res.data.belt_choices || []);
      })
      .catch((err) => {
        console.error("Form data fetch error:", err);
      });
  }, [data.gender]);


  useEffect(() => {
    if (!data.club || !data.gender) {
      setCoaches([]);
      onDataChange({ coach: "" });
      return;
    }

    axios.get(`https://api.chbtkd.ir/api/auth/coaches/?club=${data.club}&gender=${data.gender}`)
      .then((res) => setCoaches(res.data.coaches || []))
      .catch((err) => {
        console.error("Error fetching coaches:", err);
        setCoaches([]);
      });
  }, [data.club, data.gender]);

  const handleChange = (e) => {
    const { name, value } = e.target;
    onDataChange({ [name]: value });
  };
   const handleSubmit = () => {
    if (!validate()) return;
    onSubmit();
  };
  const validate = () => {
    const newErrors = {};

    if (!data.tkd_board) newErrors.tkd_board = "لطفاً هیئت را انتخاب کنید";
    if (!data.club) newErrors.club = "لطفاً یک باشگاه انتخاب کنید";
    if (!data.coach) newErrors.coach = "لطفاً مربی را انتخاب کنید";
    if (!data.belt_grade) newErrors.belt_grade = "لطفاً درجه کمربند را انتخاب کنید";
    if (!/^[\d/]+$/.test(data.belt_certificate_number || "")) newErrors.belt_certificate_number = "شماره حکم فقط شامل عدد و / باشد";
    if (!data.belt_certificate_date) newErrors.belt_certificate_date = "لطفاً تاریخ حکم را وارد کنید";
    if (!data.confirm_info) newErrors.confirm_info = "تأیید صحت اطلاعات الزامی است";

    setErrors(newErrors);

    if (Object.keys(newErrors).length > 0) {
      setModalErrorText(Object.values(newErrors)[0]);
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

      <label>
        هیئت
        <select
          name="tkd_board"
          value={data.tkd_board || ""}
          onChange={handleChange}
          className={errors.tkd_board ? "invalid" : ""}
          style={{ width: '104%' }}
        >
          <option value="">انتخاب کنید</option>
          {heyats.map((h) => (
            <option key={h.id} value={h.id}>
              {h.name}
            </option>
          ))}
        </select>
      </label>

      <label>
        باشگاه
        <select
          name="club"
          value={data.club || ""}
          onChange={handleChange}
          className={errors.club ? "invalid" : ""}
          style={{ width: '104%' }}
        >
          <option value="">انتخاب کنید</option>
          {clubs.map((c) => (
            <option key={c.id} value={c.id}>
              {c.club_name}
            </option>
          ))}
        </select>
      </label>

      <label>
        مربی
        <select
          name="coach"
          value={data.coach || ""}
          onChange={handleChange}
          className={errors.coach ? "invalid" : ""}
          disabled={!coaches.length}
          style={{ width: '104%' }}
        >
          <option value="">انتخاب کنید</option>
          {coaches.map((c) => (
            <option key={c.id} value={c.id}>
              {c.full_name}
            </option>
          ))}
        </select>
      </label>

      <label>
        درجه کمربند
        <select
          name="belt_grade"
          value={data.belt_grade || ""}
          onChange={handleChange}
          className={errors.belt_grade ? "invalid" : ""}
          style={{ width: '104%' }}
        >
          <option value="">انتخاب کنید</option>
          {beltChoices.map(([value, label], i) => (
            <option key={i} value={value}>
              {label}
            </option>
          ))}
        </select>
      </label>

      <label>
        شماره حکم
        <input
          name="belt_certificate_number"
          value={data.belt_certificate_number || ""}
          onChange={handleChange}
          className={errors.belt_certificate_number ? "invalid" : ""}
        />
      </label>

      <label className="birth-date">
        تاریخ اخذ کمربند
        <DatePicker
          calendar={persian}
          locale={persian_fa}
          maxDate={new Date()}
          value={data.belt_certificate_date || null}
          onChange={(date) =>
            date && onDataChange({ belt_certificate_date: date.format("YYYY/MM/DD") })
          }
          format="YYYY/MM/DD"
          calendarPosition="bottom-right"
          placeholder="انتخاب کنید"
        />
      </label>

      <label className="confirmcheckbox">
        <input
          id="checkboxx"
          type="checkbox"
          checked={data.confirm_info || false}
          onChange={(e) => onDataChange({ confirm_info: e.target.checked })}
        />
        <p>
          صحت اطلاعات وارد شده مورد تایید می‌باشد و در صورت تغییر متعهد به
          به‌روزرسانی هستم.
        </p>
      </label>

      
      <div className="step-buttons">
        <button onClick={onBack}>مرحله قبل</button>
        <button onClick={handleSubmit} disabled={isSubmitting}>ثبت‌نام</button>
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

export default StepThreePlayer;
