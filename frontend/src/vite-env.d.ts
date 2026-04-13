/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_AMAZON_ES_AFFILIATE_TAG?: string;
  readonly VITE_GOOGLE_CLIENT_ID?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}

interface GoogleCredentialResponse {
  credential?: string;
}

interface GoogleAccountsId {
  initialize(config: {
    client_id: string;
    callback: (response: GoogleCredentialResponse) => void;
  }): void;
  renderButton(parent: HTMLElement, options?: Record<string, string | number | boolean>): void;
  cancel(): void;
}

interface GoogleAccounts {
  id: GoogleAccountsId;
}

interface GoogleNamespace {
  accounts: GoogleAccounts;
}

interface Window {
  google?: GoogleNamespace;
}
