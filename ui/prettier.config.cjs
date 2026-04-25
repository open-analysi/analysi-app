/** @type {import("prettier").Config} */
module.exports = {
  semi: true,
  singleQuote: true,
  tabWidth: 2,
  trailingComma: 'es5',
  printWidth: 100,
  overrides: [
    {
      files: '*.json',
      options: {
        parser: 'json'
      }
    }
  ]
}; 