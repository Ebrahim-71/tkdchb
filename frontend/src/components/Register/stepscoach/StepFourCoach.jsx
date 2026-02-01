import React, { useState, useEffect } from 'react';
import './CoachRegister.css';

const StepFourCoach = ({ data, onDataChange, onSubmit, onBack }) => {
  const [errors, setErrors] = useState({});
  const [showErrorModal, setShowErrorModal] = useState(false);
  const [modalErrorText, setModalErrorText] = useState("");

  const refereeTypes = [
    { key: 'kyorogi', label: 'کیوروگی' },
    { key: 'poomseh', label: 'پومسه' },
    { key: 'hanmadang', label: 'هانمادانگ' },
  ];

  useEffect(() => {
    if (!data.refereeTypes) {
      onDataChange({ refereeTypes: {} });
    }
  }, []);

  const validate = () => {
    const newErrors = {};

    const isCoach = data.role === 'coach' || data.role === 'both';
    const isReferee = data.role === 'referee' || data.role === 'both';

    if (isCoach && !data.coachGradeNational) {
      newErrors.coachGradeNational = 'درجه ملی مربیگری الزامی است';
    }

    if (isReferee) {
      const selected = Object.entries(data.refereeTypes || {}).filter(([k, v]) => v.selected);
      if (!selected.length) {
        newErrors.refereeTypes = 'حداقل یک نوع داوری را انتخاب کنید';
      } else {
        selected.forEach(([type, info]) => {
          if (!info.gradeNational) {
            newErrors[`refereeTypes.${type}.gradeNational`] = `درجه ملی داوری ${type} الزامی است`;
          }
        });
      }
    }

    if (!data.confirm_info) {
      newErrors.confirm_info = 'تأیید اطلاعات الزامی است';
    }

    setErrors(newErrors);

    if (Object.keys(newErrors).length > 0) {
      setModalErrorText(Object.values(newErrors)[0]);
      setShowErrorModal(true);
      return false;
    }

    return true;
  };

  const handleSubmit = () => {
    if (!validate()) return;
    onSubmit();
  };

  const toggleRefereeType = (key) => {
    const current = data.refereeTypes?.[key] || {};
    onDataChange({
      refereeTypes: {
        ...data.refereeTypes,
        [key]: {
          ...current,
          selected: !current.selected,
        }
      }
    });
  };

  const handleRefereeGradeChange = (key, field, value) => {
    onDataChange({
      refereeTypes: {
        ...data.refereeTypes,
        [key]: {
          ...data.refereeTypes?.[key],
          [field]: value
        }
      }
    });
  };

  return (
    <div className="step">

      {(data.role === 'coach' || data.role === 'both') && (
        <>
          <label>
            درجه ملی مربیگری
            <select
              name="coachGradeNational"
              value={data.coachGradeNational || ''}
              onChange={(e) => onDataChange({ coachGradeNational: e.target.value })}
              className={errors.coachGradeNational ? "invalid" : ""}
            >
              <option value="">انتخاب کنید</option>
              {['درجه سه', 'درجه دو', 'درجه یک', 'ممتاز'].map((level, i) => (
                <option key={i} value={level}>{level}</option>
              ))}
            </select>
          </label>

          <label>
            درجه بین‌المللی مربیگری (اختیاری)
            <select
              name="coachGradeIntl"
              value={data.coachGradeIntl || ''}
              onChange={(e) => onDataChange({ coachGradeIntl: e.target.value })}
            >
              <option value="">انتخاب کنید</option>
              {['درجه سه', 'درجه دو', 'درجه یک', 'ممتاز'].map((level, i) => (
                <option key={i} value={level}>{level}</option>
              ))}
            </select>
          </label>
        </>
      )}

      {(data.role === 'referee' || data.role === 'both') && (
        <>
          <label>نوع داوری (حداقل یک مورد):</label>
          <div className="referee-type-row">
            {refereeTypes.map(({ key, label }) => (
              <div key={key} className="referee-type-box">
                <label className="referee-checkbox">
                  <input
                    type="checkbox"
                    checked={!!data.refereeTypes?.[key]?.selected}
                    onChange={() => toggleRefereeType(key)}
                  />
                  <span>{label}</span>
                </label>

                {data.refereeTypes?.[key]?.selected && (
                  <div className="referee-grade-section">
                    <label>
                      درجه ملی داوری {label}
                      <select
                        value={data.refereeTypes?.[key]?.gradeNational || ''}
                        onChange={(e) => handleRefereeGradeChange(key, 'gradeNational', e.target.value)}
                        className={errors[`refereeTypes.${key}.gradeNational`] ? "invalid" : ""}
                      >
                        <option value="">انتخاب کنید</option>
                        {['درجه سه', 'درجه دو', 'درجه یک', 'ممتاز'].map((level, i) => (
                          <option key={i} value={level}>{level}</option>
                        ))}
                      </select>
                    </label>

                    <label>
                      درجه بین‌المللی داوری {label} (اختیاری)
                      <select
                        value={data.refereeTypes?.[key]?.gradeIntl || ''}
                        onChange={(e) => handleRefereeGradeChange(key, 'gradeIntl', e.target.value)}
                      >
                        <option value="">انتخاب کنید</option>
                        {['درجه سه', 'درجه دو', 'درجه یک', 'ممتاز'].map((level, i) => (
                          <option key={i} value={level}>{level}</option>
                        ))}
                      </select>
                    </label>
                  </div>
                )}
              </div>
            ))}
          </div>
        </>
      )}

        <label className='confirm'>
          <input
            className='c-chekbox'
            type="checkbox"
            checked={data.confirm_info || false}
            onChange={(e) => onDataChange({ confirm_info: e.target.checked })}
          />
          <p>صحت اطلاعات وارد شده مورد تایید می‌باشد و در صورت تغییر متعهد به به‌روزرسانی هستم.</p>
        </label>

      <div className="step-buttons">
        <button onClick={onBack}>مرحله قبل</button>
        <button onClick={handleSubmit}>ثبت‌نام</button>
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

export default StepFourCoach;
