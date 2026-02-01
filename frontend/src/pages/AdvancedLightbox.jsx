import React, { useEffect, useState, useCallback, useRef } from 'react';
import './AdvancedLightbox.css';

const AdvancedLightbox = ({ images, initialIndex = 0, onClose }) => {
  const [currentIndex, setCurrentIndex] = useState(initialIndex);
  const [isDragging, setIsDragging] = useState(false);
  const [position, setPosition] = useState({ x: 0, y: 0 });
  const [zoomed, setZoomed] = useState(false);
  const dragStart = useRef({ x: 0, y: 0 });

  const prevImage = useCallback(() => {
    setCurrentIndex((prev) => (prev + images.length - 1) % images.length);
    resetZoom();
  }, [images.length]);

  const nextImage = useCallback(() => {
    setCurrentIndex((prev) => (prev + 1) % images.length);
    resetZoom();
  }, [images.length]);

  const resetZoom = () => {
    setZoomed(false);
    setPosition({ x: 0, y: 0 });
  };

  const handleKey = useCallback(
    (e) => {
      if (e.key === 'ArrowLeft') prevImage();
      else if (e.key === 'ArrowRight') nextImage();
      else if (e.key === 'Escape') onClose();
    },
    [prevImage, nextImage, onClose]
  );

  useEffect(() => {
    window.addEventListener('keydown', handleKey);
    return () => window.removeEventListener('keydown', handleKey);
  }, [handleKey]);

  const handleMouseDown = (e) => {
    if (!zoomed) return;
    setIsDragging(true);
    dragStart.current = { x: e.clientX - position.x, y: e.clientY - position.y };
  };

  const handleMouseMove = (e) => {
    if (!isDragging || !zoomed) return;
    const newX = e.clientX - dragStart.current.x;
    const newY = e.clientY - dragStart.current.y;
    setPosition({ x: newX, y: newY });
  };

  const handleMouseUp = () => setIsDragging(false);

  return (
    <div className="lightbox-overlay" onClick={onClose}>
      <div
        className="lightbox-content"
        onClick={(e) => e.stopPropagation()}
        onMouseMove={handleMouseMove}
        onMouseUp={handleMouseUp}
        onMouseLeave={handleMouseUp}
      >
        <button className="lightbox-close" onClick={onClose}>x</button>
        <button className="lightbox-nav left" onClick={prevImage}>›</button>

        <img
          src={images[currentIndex]}
          alt=""
          className={`lightbox-image ${zoomed ? 'zoomed' : ''}`}
          style={{
            transform: zoomed ? `scale(2) translate(${position.x / 2}px, ${position.y / 2}px)` : 'scale(1)',
            cursor: zoomed ? (isDragging ? 'grabbing' : 'grab') : 'zoom-in',
          }}
          onMouseDown={handleMouseDown}
          onDoubleClick={() => setZoomed(!zoomed)}
          draggable={false}
        />

        <button className="lightbox-nav right" onClick={nextImage}>‹</button>
      </div>
    </div>
  );
};

export default AdvancedLightbox;
