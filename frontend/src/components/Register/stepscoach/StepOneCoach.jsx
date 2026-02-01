import React, { useState } from 'react';
import DatePicker from 'react-multi-date-picker';
import DateObject from 'react-date-object';
import persian from 'react-date-object/calendars/persian';
import persian_fa from 'react-date-object/locales/persian_fa';
import './CoachRegister.css';
import axios from 'axios';

const StepOneCoach = ({ data, onNext, onDataChange }) => {
  const [error, setError] = useState('');
  const [touched, setTouched] = useState({});
  const [nationalCodeExists, setNationalCodeExists] = useState(false);

  
  const toEnglishNumber = (str) => {
  const persianNumbers = ['۰','۱','۲','۳','۴','۵','۶','۷','۸','۹'];
  const englishNumbers = ['0','1','2','3','4','5','6','7','8','9'];
  let output = str;
  persianNumbers.forEach((num, idx) => {
    const regex = new RegExp(num, 'g');
    output = output.replace(regex, englishNumbers[idx]);
  });
  return output;
};

  const calculateAge = (birthDateStr) => {
  if (!birthDateStr) return 0;
  const normalizedDateStr = toEnglishNumber(birthDateStr);  // تبدیل اعداد فارسی به انگلیسی
  const birth = new DateObject({ date: normalizedDateStr, format: "YYYY/MM/DD", calendar: persian });
  const today = new DateObject({ calendar: persian });
  let age = today.year - birth.year;
  if (today.month < birth.month || (today.month === birth.month && today.day < birth.day)) {
    age--;
  }
  return age;
};
const handleChange = (e) => {
  const { name, value } = e.target;
  onDataChange({ [name]: value });
  setTouched(prev => ({ ...prev, [name]: true }));

  if (name === 'national_code' && value.length === 10) {
    fetch(`https://api.chbtkd.ir/api/auth/check-national-code/?code=${value}`)
      .then((res) => res.json())
      .then((data) => {
        if (data.exists) {
          setError('این کد ملی قبلاً ثبت شده است.');
          setNationalCodeExists(true);
        } else {
          setNationalCodeExists(false);
        }
      })
      .catch((err) => {
        console.error('خطا در بررسی کد ملی:', err);
      });
  }
};


  const handleSubmit = (e) => {
    e.preventDefault();

    const {
      first_name,
      last_name,
      father_name,
      national_code,
      birth_date,
      gender,
    } = data;
    
    if (!first_name || !last_name || !father_name || !national_code || !birth_date || !gender) {
      return setError('لطفاً همه فیلدها را کامل کنید.');
    }
    
  if (nationalCodeExists) {
    return setError('این کد ملی قبلاً ثبت شده است.');
  }

    const isPersian = (text) => /^[\u0600-\u06FF\s]+$/.test(text);
    const isNumeric = (text) => /^\d+$/.test(text);

    if (![first_name, last_name, father_name].every(isPersian)) {
      return setError('فیلدها باید با حروف فارسی وارد شوند.');
    }

    if (!isNumeric(national_code) || national_code.length !== 10) {
      return setError('کد ملی باید ۱۰ رقم و فقط شامل عدد باشد.');
    }
    
    const age = calculateAge(birth_date);
    if (gender === 'female' && age < 21) {
      return setError('حداقل سن برای خانم‌ها باید ۲۱ سال باشد.');
    }
    if (gender === 'male' && age < 22) {
      return setError('حداقل سن برای آقایان باید ۲۲ سال باشد.');
    }

    setError('');
    onNext();
  };

  return (
    <form className="step" onSubmit={handleSubmit}>
      <h2>مشخصات فردی</h2>

      <label>
        نام:
        <input
          type="text"
          name="first_name"
          value={data.first_name || ''}
          onChange={handleChange}
          className={touched.first_name && !data.first_name ? 'invalid' : ''}
        />
      </label>

      <label>
        نام خانوادگی:
        <input
          type="text"
          name="last_name"
          value={data.last_name || ''}
          onChange={handleChange}
          className={touched.last_name && !data.last_name ? 'invalid' : ''}
        />
      </label>

      <label>
        نام پدر:
        <input
          type="text"
          name="father_name"
          value={data.father_name || ''}
          onChange={handleChange}
          className={touched.father_name && !data.father_name ? 'invalid' : ''}
        />
      </label>

      <label>
        کد ملی:
        <input
          type="text"
          name="national_code"
          value={data.national_code || ''}
          onChange={handleChange}
          maxLength="10"
          className={touched.national_code && !data.national_code ? 'invalid' : ''}
        />
      </label>

      <label>
        جنسیت:
        <select
          name="gender"
          value={data.gender || ''}
          onChange={handleChange}
          className={touched.gender && !data.gender ? 'invalid' : ''}
          style={{ width: '104%' }}
        >
          <option value="">انتخاب کنید</option>
          <option value="male">مرد</option>
          <option value="female">زن</option>
        </select>
      </label>

      <label className="birth-date">
  تاریخ تولد:
  <DatePicker
    calendar={persian}
    locale={persian_fa}
    maxDate={new Date()}
    value={data.birth_date || null}
    onChange={(date) =>
      date && onDataChange({ birth_date: date.format("YYYY/MM/DD") })
    }
    format="YYYY/MM/DD"
    calendarPosition="bottom-right"
    placeholder="انتخاب کنید"
  />
</label>



      <div className="step-buttons">
        <button type="submit">مرحله بعد</button>
      </div>

      {error && (
        <div className="modal-error-overlay">
          <div className="modal-error-box">
            <p>{error}</p>
            <button onClick={() => setError('')}>بستن</button>
          </div>
        </div>
      )}
    </form>
  );
};

export default StepOneCoach;
