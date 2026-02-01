import React, { useState } from 'react';
import './ClubRegister.css';

const StepOneClub = ({ data, onDataChange, onNext }) => {
  const [errors, setErrors] = useState({});
  const [showErrorModal, setShowErrorModal] = useState(false);

  const handleChange = (e) => {
   onDataChange({ [e.target.name]: e.target.value.trim() });
  };

  const validate = () => {
    const newErrors = {};
    if (!data.club_name) newErrors.club_name = 'نام باشگاه الزامی است';
    if (!data.founder_name) newErrors.founder_name = 'نام مؤسس الزامی است';
    if (!/^\d{10}$/.test(data.founder_national_code || '')) newErrors.founder_national_code = 'کد ملی باید ۱۰ رقم عددی باشد';
    if (!data.club_type) newErrors.club_type = 'نوع باشگاه را انتخاب کنید';
    if (!data.activity_description || data.activity_description.length < 10)
      newErrors.activity_description = 'توضیح فعالیت باید حداقل ۱۰ کاراکتر باشد';

    setErrors(newErrors);

    if (Object.keys(newErrors).length > 0) {
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
      <h2> اطلاعات اولیه باشگاه</h2>

      <label>نام باشگاه:
        <input
          type="text"
          name="club_name"
          value={data.club_name || ''}
          onChange={handleChange}
          className={errors.club_name ? 'invalid' : ''}
        />
      </label>

      <label>نام مؤسس:
        <input
          type="text"
          name="founder_name"
          value={data.founder_name || ''}
          onChange={handleChange}
          className={errors.founder_name ? 'invalid' : ''}
        />
      </label>

      <label>کد ملی مؤسس:
        <input
          type="text"
          name="founder_national_code"
          value={data.founder_national_code || ''}
          onChange={handleChange}
          maxLength={10}
          className={errors.founder_national_code ? 'invalid' : ''}
        />
      </label>

      <label>نوع باشگاه:
        <select
        
        
          name="club_type"
          value={data.club_type || ''}
          onChange={handleChange}
          className={errors.club_type ? 'invalid' : ''}
          style={{ width: '104%' }}
        >
          <option value="">انتخاب کنید</option>
          <option value="private">خصوصی</option>
          <option value="governmental">دولتی</option>
          <option value="other">سایر</option>
        </select>
      </label>

      <label>توضیح فعالیت:
        <textarea
          name="activity_description"
          value={data.activity_description || ''}
          onChange={handleChange}
          className={errors.activity_description ? 'invalid' : ''}
        />
      </label>

      <div className="step-buttons">
        <button type="button" onClick={handleNext}>مرحله بعد</button>
      </div>

      {showErrorModal && (
        <div className="modal-error-overlay">
          <div className="modal-error-box">
            {Object.values(errors).map((err, i) => (
              <p key={i}>{err}</p>
            ))}
            <button onClick={() => setShowErrorModal(false)}>بستن</button>
          </div>
        </div>
      )}
    </div>
  );
};

export default StepOneClub;
