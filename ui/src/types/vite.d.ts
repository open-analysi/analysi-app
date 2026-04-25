declare module '/vite.svg' {
  const content: string;
  export default content;
}

// Properly type import.meta.env
interface ImportMetaEnv {
  DEV: boolean;
  PROD: boolean;
  SSR: boolean;
  MODE: string;
  BASE_URL: string;
  VITE_API_URL?: string;
  [key: string]: string | boolean | undefined;
}

interface ImportMeta {
  env: ImportMetaEnv;
}
