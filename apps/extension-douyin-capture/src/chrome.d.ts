type ChromeStorageChange = {
  oldValue?: unknown;
  newValue?: unknown;
};

declare const chrome: {
  runtime: {
    id?: string;
    getManifest(): { version: string; name?: string };
    getURL(path: string): string;
    sendMessage(message: unknown): Promise<any>;
    lastError?: { message?: string };
    onInstalled: {
      addListener(callback: () => void): void;
    };
    onMessage: {
      addListener(
        callback: (
          message: unknown,
          sender: { tab?: { id?: number; url?: string } } | unknown,
          sendResponse: (response: unknown) => void
        ) => boolean | void
      ): void;
      removeListener(
        callback: (
          message: unknown,
          sender: { tab?: { id?: number; url?: string } } | unknown,
          sendResponse: (response: unknown) => void
        ) => boolean | void
      ): void;
    };
  };
  storage: {
    onChanged: {
      addListener(callback: (changes: Record<string, ChromeStorageChange>, areaName: string) => void): void;
      removeListener(callback: (changes: Record<string, ChromeStorageChange>, areaName: string) => void): void;
    };
    sync: {
      get(key: string): Promise<Record<string, unknown>>;
      set(items: Record<string, unknown>): Promise<void>;
      remove(key: string | string[]): Promise<void>;
    };
    local: {
      get(key: string): Promise<Record<string, unknown>>;
      set(items: Record<string, unknown>): Promise<void>;
      remove(key: string | string[]): Promise<void>;
    };
  };
  tabs: {
    query(queryInfo: { active?: boolean; currentWindow?: boolean; url?: string | string[] }): Promise<Array<{ id?: number; url?: string; windowId?: number }>>;
    create(createProperties: { url?: string; active?: boolean }): Promise<{ id?: number; url?: string }>;
    update(tabId: number, updateProperties: { url?: string; active?: boolean }): Promise<{ id?: number; url?: string }>;
    sendMessage(tabId: number, message: unknown): Promise<any>;
    reload(tabId: number, reloadProperties?: { bypassCache?: boolean }): Promise<void>;
    captureVisibleTab(windowId?: number | null, options?: { format?: "png" | "jpeg"; quality?: number }): Promise<string>;
    onRemoved: {
      addListener(callback: (tabId: number) => void): void;
    };
  };
  windows: {
    update(windowId: number, updateInfo: { focused?: boolean }): Promise<void>;
  };
  scripting: {
    executeScript(options: { target: { tabId: number }; files: string[] }): Promise<unknown[]>;
    executeScript<T = unknown>(options: { target: { tabId: number }; func: (...args: any[]) => T; args?: unknown[] }): Promise<Array<{ result?: Awaited<T> }>>;
  };
  debugger: {
    attach(target: { tabId: number }, requiredVersion: string): Promise<void>;
    detach(target: { tabId: number }): Promise<void>;
    sendCommand<T = unknown>(target: { tabId: number }, method: string, commandParams?: Record<string, unknown>): Promise<T>;
    onEvent: {
      addListener(callback: (source: { tabId?: number }, method: string, params?: Record<string, unknown>) => void): void;
    };
    onDetach: {
      addListener(callback: (source: { tabId?: number }, reason: string) => void): void;
    };
  };
};
