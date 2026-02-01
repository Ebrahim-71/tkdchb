import React, { useState } from 'react';
import './PaginatedList.css';

const PaginatedList = ({ items, renderItem, itemsPerPage = 4 }) => {
  const [page, setPage] = useState(1);
  const totalPages = Math.ceil(items.length / itemsPerPage);

  const currentItems = items.slice((page - 1) * itemsPerPage, page * itemsPerPage);

  const handlePageClick = (newPage) => {
    if (newPage >= 1 && newPage <= totalPages) {
      setPage(newPage);
    }
  };

  return (
    <div className='maainlist' >
      {currentItems.map((item, index) => (
        <React.Fragment key={index}>
          {renderItem(item, index)}
        </React.Fragment>
      ))}

      {totalPages > 1 && (
        <div className="pagination-controls">
          {[...Array(totalPages)].map((_, i) => (
            <button
              key={i}
              className={`pagination-button ${i + 1 === page ? 'active' : ''}`}
              onClick={() => handlePageClick(i + 1)}
            >
              {i + 1}
            </button>
          ))}
        </div>
      )}
    </div>
  );
};

export default PaginatedList;
