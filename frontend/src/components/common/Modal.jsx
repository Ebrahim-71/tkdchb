import React from "react";
import "./Modal.css";

const Modal = ({ title, message, onConfirm, onCancel }) => {
  return (
    <div className="modal-overlay">
      <div className="modal-box">
        <h3 className="modal-title">{title}</h3>
        <p className="modal-message">{message}</p>
        <div className="modal-actions">
          <button className="cancel-btn" onClick={onCancel}>
            خیر
          </button>
          <button className="confirm-btn" onClick={onConfirm}>
            بله
          </button>
        </div>
      </div>
    </div>
  );
};

export default Modal;
