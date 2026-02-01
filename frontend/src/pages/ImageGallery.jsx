import React, { useState } from 'react';
import AdvancedLightbox from './AdvancedLightbox';

const ImageGallery = ({ images }) => {
  const [isOpen, setIsOpen] = useState(false);
  const [selectedIndex, setSelectedIndex] = useState(0);

  if (!images || images.length === 0) return null;

  const openLightbox = (index) => {
    setSelectedIndex(index);
    setIsOpen(true);
  };

  return (
    <>
      <div className="thumbnail-gallery">
        {images.map((img, i) => (
          <img
            key={i}
            src={img}
            alt={`image-${i}`}
            className="thumbnail"
            onClick={() => openLightbox(i)}
          />
        ))}
      </div>
      {isOpen && (
        <AdvancedLightbox
          images={images}
          initialIndex={selectedIndex}
          onClose={() => setIsOpen(false)}
        />
      )}
    </>
  );
};

export default ImageGallery;
