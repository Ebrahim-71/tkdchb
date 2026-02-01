import React, { useState } from 'react';
import StepOne from './steps/StepOne';
import StepTwo from './steps/StepTwo';
import StepThree from './steps/StepThree';
import StepFour from './steps/StepFour';
import './MultiStepForm.css';

const MultiStepForm = () => {
  const [step, setStep] = useState(1);
  const [formData, setFormData] = useState({});

  const nextStep = () => setStep((prev) => prev + 1);
  const prevStep = () => setStep((prev) => prev - 1);

  const handleDataChange = (data) => {
    setFormData((prev) => ({ ...prev, ...data }));
  };

  const steps = {
    1: <StepOne data={formData} onNext={handleNext} onDataChange={(changed) => setFormData((prev) => ({ ...prev, ...changed }))}/>,
    2: <StepTwo onNext={nextStep} onBack={prevStep} data={formData} onDataChange={handleDataChange} />,
    3: <StepThree onNext={nextStep} onBack={prevStep} data={formData} onDataChange={handleDataChange} />,
    4: <StepFour onBack={prevStep} data={formData} />,
  };

  return (
    <div className="multi-step-form">
      <div className="form-image-side" />
      <div className="form-content-side">
        {steps[step]}
      </div>
    </div>
  );
};

export default MultiStepForm;
