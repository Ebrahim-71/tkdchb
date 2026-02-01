import React, { useState } from 'react';
import provincesData from '../provincesData.js';
import './CoachRegister.css';

const StepTwoCoach = ({ data, onNext, onBack, onDataChange }) => {
  const [invalidFields, setInvalidFields] = useState([]);
  const [customErrors, setCustomErrors] = useState([]);
  const [showErrorModal, setShowErrorModal] = useState(false);

  const validate = () => {
    const required = ['province', 'county', 'city', 'address', 'profile_image'];
    const invalids = [];
    const errors = [];

    required.forEach(field => {
      if (!data[field]) {
        invalids.push(field);
        switch (field) {
          case 'province':
            errors.push('لطفاً استان را انتخاب کنید.');
            break;
          case 'county':
            errors.push('لطفاً شهرستان را انتخاب کنید.');
            break;
          case 'city':
            errors.push('لطفاً شهر را انتخاب کنید.');
            break;
          case 'address':
            errors.push('آدرس نمی‌تواند خالی باشد.');
            break;
          case 'profile_image':
            errors.push('بارگذاری عکس پرسنلی الزامی است.');
            break;
          default:
            errors.push(`فیلد ${field} الزامی است.`);
        }
      }
    });

    // اعتبارسنجی آدرس
    if (data.address) {
      const faAddressRegex = /^[\u0600-\u06FF0-9\s،.\-]+$/;
      if (!faAddressRegex.test(data.address)) {
        if (!invalids.includes('address')) invalids.push('address');
        errors.push('آدرس شامل کاراکتر غیرمجاز است.');
      } else if (data.address.length < 10 || data.address.length > 300) {
        if (!invalids.includes('address')) invalids.push('address');
        errors.push('آدرس باید بین ۱۰ تا ۳۰۰ کاراکتر باشد.');
      }
    }

    // اعتبارسنجی فایل تصویر
   if (data.profile_image) {
  const isJpg = ['image/jpeg', 'image/jpg'].includes(data.profile_image.type);
  const isUnderSize = data.profile_image.size <= 200 * 1024;
  if (!isJpg || !isUnderSize) {
    if (!invalids.includes('profile_image')) invalids.push('profile_image');
    errors.push('عکس پرسنلی باید JPG و حداکثر ۲۰۰ کیلوبایت باشد.');
  }
}


    setInvalidFields(invalids);
    setCustomErrors(errors);
    setShowErrorModal(errors.length > 0);

    return errors.length === 0;
  };

  const handleChange = (e) => {
  const { name, value } = e.target;
  if (name === 'province') {
    onDataChange({ province: value, county: '', city: '' });
  } else if (name === 'county') {
    onDataChange({ county: value, city: '' });
  } else {
    onDataChange({ [name]: value });
  }
};

  const handleFileChange = (e) => {
    const file = e.target.files[0];
    if (file) {
      onDataChange({ profile_image: file });
    }
  };

  const handleNext = () => {
    if (validate()) {
      onNext();
    }
  };

  return (
    <div className="step">
      <h2>اطلاعات محل سکونت و تصویر</h2>

      <label>
        استان:
        <select
          name="province"
          value={data.province || ''}
          onChange={handleChange}
          className={invalidFields.includes('province') ? 'invalid' : ''}
          style={{ width: '104%' }}
        >
          <option value="">انتخاب کنید</option>
          {Object.keys(provincesData).map(prov => (
            <option key={prov} value={prov}>{prov}</option>
          ))}
        </select>
      </label>

      {data.province && (
        <label>
          شهرستان:
          <select
            name="county"
            value={data.county || ''}
            onChange={handleChange}
            className={invalidFields.includes('county') ? 'invalid' : ''}
            style={{ width: '104%' }}
          >
            <option value="">انتخاب کنید</option>
            {Object.keys(provincesData[data.province]).map(county => (
              <option key={county} value={county}>{county}</option>
            ))}
          </select>
        </label>
      )}

      {data.county && (
        <label>
          شهر:
          <select
            name="city"
            value={data.city || ''}
            onChange={handleChange}
            className={invalidFields.includes('city') ? 'invalid' : ''}
            style={{ width: '104%' }}
          >
            <option value="">انتخاب کنید</option>
            {provincesData[data.province][data.county].map(city => (
              <option key={city} value={city}>{city}</option>
            ))}
          </select>
        </label>
      )}

      <label>
        آدرس:
        <textarea
          name="address"
          value={data.address || ''}
          onChange={handleChange}
          className={invalidFields.includes('address') ? 'invalid' : ''}
        />
      </label>

      <label>
        عکس پرسنلی:
        <input
          type="file"
           name="profile_image"
          accept="image/jpeg,image/jpg"
          onChange={handleFileChange}
          className={invalidFields.includes('profile_image') ? 'invalid' : ''}
        />
        <span style={{ fontSize: '0.8rem', color: 'gray', marginTop: '4px', display: 'block' }}>
          فرمت مجاز: JPG - حداکثر حجم: ۲۰۰ کیلوبایت
        </span>
      </label>


      <div className="step-buttons">
        <button type="button" onClick={onBack}>مرحله قبل</button>
        <button type="button" onClick={handleNext}>مرحله بعد</button>
      </div>

      {showErrorModal && (
        <div className="modal-error-overlay">
          <div className="modal-error-box">
            {customErrors.map((err, index) => (
              <p key={index}>{err}</p>
            ))}
            <button onClick={() => setShowErrorModal(false)}>باشه</button>
          </div>
        </div>
      )}
    </div>
  );
};

export default StepTwoCoach;
