import React, { useRef, useState } from 'react';
import './ClubRegister.css';

const StepThreeClub = ({ data, onDataChange, onBack, onSubmit }) => {
  const fileInputRef = useRef();
  const [invalidFields, setInvalidFields] = useState([]);
  const [customErrors, setCustomErrors] = useState([]);
  const [showErrorModal, setShowErrorModal] = useState(false);

  const handleChange = (e) => {
    const { name, value, type, checked, files } = e.target;

    if (type === 'file') {
      onDataChange({ license_image: files[0] });
    } else if (type === 'checkbox') {
      onDataChange({ [name]: checked });
    } else {
      onDataChange({ [name]: value });
    }
  };

  const validate = () => {
    const required = ['license_number', 'federation_id', 'license_image'];
    const invalids = [];
    const errors = [];

    required.forEach(field => {
      if (!data[field]) {
        invalids.push(field);
        switch (field) {
          case 'license_number':
            errors.push('شماره مجوز الزامی است.');
            break;
          case 'federation_id':
            errors.push('شناسه ثبت در فدراسیون الزامی است.');
            break;
          case 'license_image':
            errors.push('بارگذاری تصویر مجوز الزامی است.');
            break;
        }
      }
    });

    // شماره مجوز فقط عدد یا / باشد
    if (data.license_number && !/^[0-9/]+$/.test(data.license_number)) {
      if (!invalids.includes('license_number')) invalids.push('license_number');
      errors.push('شماره مجوز فقط شامل عدد و "/" باشد.');
    }

    // فایل عکس
    if (data.license_image) {
      const validTypes = ['image/jpeg', 'image/jpg', 'image/png'];
      const isValidType = validTypes.includes(data.license_image.type);
      const isUnderSize = data.license_image.size <= 200 * 1024;
      if (!isValidType) {
        if (!invalids.includes('license_image')) invalids.push('license_image');
        errors.push('فرمت تصویر باید JPG یا PNG باشد.');
      }
      if (!isUnderSize) {
        if (!invalids.includes('license_image')) invalids.push('license_image');
        errors.push('حجم تصویر نباید بیشتر از ۲۰۰ کیلوبایت باشد.');
      }
    }

    // تایید نهایی
    if (!data.confirm_info) {
      errors.push('لطفاً صحت اطلاعات را تأیید کنید.');
      invalids.push('confirm_info');
    }

    setInvalidFields(invalids);
    setCustomErrors(errors);
    setShowErrorModal(errors.length > 0);

    return errors.length === 0;
  };

  const handleSubmit = () => {
    if (validate()) {
      onSubmit();
    }
  };

  return (
    <div className="step">
      <h2> اطلاعات حقوقی باشگاه</h2>

      <label>
        شماره مجوز:
        <input
          type="text"
          name="license_number"
          value={data.license_number || ''}
          onChange={handleChange}
          className={invalidFields.includes('license_number') ? 'invalid' : ''}
        />
      </label>

      <label>
        شناسه ثبت در فدراسیون:
        <input
          type="text"
          name="federation_id"
          value={data.federation_id || ''}
          onChange={handleChange}
          className={invalidFields.includes('federation_id') ? 'invalid' : ''}
        />
      </label>

      <label>
        تصویر مجوز باشگاه:
        <input
          type="file"
          name="license_image"
          accept="image/jpeg,image/jpg,image/png"
          ref={fileInputRef}
          onChange={handleChange}
          className={invalidFields.includes('license_image') ? 'invalid' : ''}
        />
        <span style={{ fontSize: '0.8rem', color: 'gray' }}>
          فرمت مجاز: JPG یا PNG - حداکثر حجم: ۲۰۰ کیلوبایت
        </span>
      </label>

      <div className="confirm">
        <input
          type="checkbox"
          id="confirm_info"
          name="confirm_info"
          checked={data.confirm_info || false}
          onChange={handleChange}
          className="c-chekbox"
        />
        <label htmlFor="confirm_info" style={{ marginRight: '0.5rem' }}>
          <p>صحت اطلاعات وارد شده مورد تایید می‌باشد و در صورت تغییر متعهد به به‌روزرسانی هستم.</p>
        </label>
      </div>

      <div className="step-buttons">
        <button type="button" onClick={onBack}>مرحله قبل</button>
        <button type="button" onClick={handleSubmit}>ثبت نهایی</button>
      </div>

      {showErrorModal && (
        <div className="modal-error-overlay">
          <div className="modal-error-box">
            {customErrors.map((err, i) => (
              <p key={i}>{err}</p>
            ))}
            <button onClick={() => setShowErrorModal(false)}>باشه</button>
          </div>
        </div>
      )}
    </div>
  );
};

export default StepThreeClub;
