import React from 'react';

import { ChevronLeftIcon, ChevronRightIcon } from '@heroicons/react/24/outline';

interface PaginationProps {
  currentPage: number;
  totalPages: number;
  totalItems: number;
  itemsPerPage: number;
  onPageChange: (page: number) => void;
}

export const Pagination: React.FC<PaginationProps> = ({
  currentPage,
  totalPages,
  totalItems,
  itemsPerPage,
  onPageChange,
}) => {
  if (totalPages <= 1) return null;

  return (
    <div className="flex items-center justify-between px-4 py-1.5 sm:px-6">
      <div className="flex flex-1 justify-between sm:hidden">
        <button
          onClick={() => onPageChange(Math.max(1, currentPage - 1))}
          disabled={currentPage === 1}
          className={`relative inline-flex items-center rounded-md border border-dark-600 ${
            currentPage === 1
              ? 'bg-dark-800 text-gray-500 cursor-not-allowed'
              : 'bg-dark-700 text-gray-200 hover:bg-dark-600'
          } px-3 py-1 text-sm font-medium`}
        >
          Previous
        </button>
        <button
          onClick={() => onPageChange(Math.min(totalPages, currentPage + 1))}
          disabled={currentPage === totalPages}
          className={`relative ml-3 inline-flex items-center rounded-md border border-dark-600 ${
            currentPage === totalPages
              ? 'bg-dark-800 text-gray-500 cursor-not-allowed'
              : 'bg-dark-700 text-gray-200 hover:bg-dark-600'
          } px-3 py-1 text-sm font-medium`}
        >
          Next
        </button>
      </div>
      <div className="hidden sm:flex sm:flex-1 sm:items-center sm:justify-between">
        <div>
          <p className="text-sm text-gray-400">
            Showing <span className="font-medium">{(currentPage - 1) * itemsPerPage + 1}</span> to{' '}
            <span className="font-medium">{Math.min(currentPage * itemsPerPage, totalItems)}</span>{' '}
            of <span className="font-medium">{totalItems}</span> results
          </p>
        </div>
        <div>
          <nav
            className="isolate inline-flex -space-x-px rounded-md shadow-xs"
            aria-label="Pagination"
          >
            <button
              onClick={() => onPageChange(Math.max(1, currentPage - 1))}
              disabled={currentPage === 1}
              className={`relative inline-flex items-center rounded-l-md px-2 py-1 ${
                currentPage === 1
                  ? 'text-gray-500 cursor-not-allowed'
                  : 'text-gray-400 hover:bg-dark-600 hover:text-white'
              }`}
            >
              <span className="sr-only">Previous</span>
              <ChevronLeftIcon className="h-5 w-5" aria-hidden="true" />
            </button>

            {/* Page numbers with sliding window */}
            {(() => {
              const pageNumbers = [];
              const maxButtons = 5;
              let startPage = Math.max(1, currentPage - Math.floor(maxButtons / 2));
              const endPage = Math.min(totalPages, startPage + maxButtons - 1);

              // Adjust start if we're near the end
              if (endPage - startPage + 1 < maxButtons) {
                startPage = Math.max(1, endPage - maxButtons + 1);
              }

              // Add first page and ellipsis if needed
              if (startPage > 1) {
                pageNumbers.push(
                  <button
                    key={1}
                    onClick={() => onPageChange(1)}
                    className="relative inline-flex items-center px-3 py-1 text-sm font-semibold text-gray-300 hover:bg-dark-600 hover:text-white"
                  >
                    1
                  </button>
                );
                if (startPage > 2) {
                  pageNumbers.push(
                    <span
                      key="ellipsis-start"
                      className="relative inline-flex items-center px-2 py-1 text-sm text-gray-500"
                    >
                      ...
                    </span>
                  );
                }
              }

              // Add page number buttons
              for (let i = startPage; i <= endPage; i++) {
                pageNumbers.push(
                  <button
                    key={i}
                    onClick={() => onPageChange(i)}
                    className={`relative inline-flex items-center px-3 py-1 text-sm font-semibold ${
                      i === currentPage
                        ? 'z-10 bg-primary text-white focus:z-20'
                        : 'text-gray-300 hover:bg-dark-600 hover:text-white'
                    }`}
                  >
                    {i}
                  </button>
                );
              }

              // Add ellipsis and last page if needed
              if (endPage < totalPages) {
                if (endPage < totalPages - 1) {
                  pageNumbers.push(
                    <span
                      key="ellipsis-end"
                      className="relative inline-flex items-center px-2 py-1 text-sm text-gray-500"
                    >
                      ...
                    </span>
                  );
                }
                pageNumbers.push(
                  <button
                    key={totalPages}
                    onClick={() => onPageChange(totalPages)}
                    className="relative inline-flex items-center px-3 py-1 text-sm font-semibold text-gray-300 hover:bg-dark-600 hover:text-white"
                  >
                    {totalPages}
                  </button>
                );
              }

              return pageNumbers;
            })()}

            <button
              onClick={() => onPageChange(Math.min(totalPages, currentPage + 1))}
              disabled={currentPage === totalPages}
              className={`relative inline-flex items-center rounded-r-md px-2 py-1 ${
                currentPage === totalPages
                  ? 'text-gray-500 cursor-not-allowed'
                  : 'text-gray-400 hover:bg-dark-600 hover:text-white'
              }`}
            >
              <span className="sr-only">Next</span>
              <ChevronRightIcon className="h-5 w-5" aria-hidden="true" />
            </button>
          </nav>
        </div>
      </div>
    </div>
  );
};
