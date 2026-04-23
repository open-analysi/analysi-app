export default {
  '*.{ts,tsx}': (files) => {
    const filtered = files.filter((f) => !f.includes('/generated/'));
    if (filtered.length === 0) return [];
    return [
      `eslint --fix --max-warnings 50 ${filtered.join(' ')}`,
      `prettier --write ${filtered.join(' ')}`,
      `vitest related ${filtered.join(' ')} --run --reporter=dot`,
    ];
  },
  '*.{json,md}': ['prettier --write'],
}; 