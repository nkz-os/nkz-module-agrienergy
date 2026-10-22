/**
 * Type augmentations for host-provided externals.
 * The published npm packages may ship incomplete .d.ts — redeclare here.
 */

declare module '@nekazari/sdk' {
  export function useAuth(): {
    getToken: () => string | undefined;
    getTenantId: () => string | undefined;
    hasRole: (role: string) => boolean;
    hasAnyRole: (roles: string[]) => boolean;
    isAuthenticated: boolean;
    user: { id?: string; username?: string; email?: string; roles: string[]; tenant?: string } | null;
  };
  export function useViewer(): { selectedEntityId: string | null; toggleLayer: (id: string) => void; selectEntity: (id: string, type?: string) => void };
  export function useViewerOptional(): { selectedEntityId: string | null; toggleLayer: (id: string) => void; selectEntity: (id: string, type?: string) => void } | null;
  export function useTranslation(): { t: (key: string, opts?: any) => string };
  export { Trans, Translation } from 'react-i18next';
  export { default as i18n } from 'i18next';
  export class NKZClient {
    constructor(options: { baseUrl: string; getToken?: () => string | undefined; getTenantId?: () => string | undefined });
    get<T = any>(path: string): Promise<T>;
    post<T = any, B = any>(path: string, body?: B): Promise<T>;
    put<T = any, B = any>(path: string, body?: B): Promise<T>;
    patch<T = any, B = any>(path: string, body?: B): Promise<T>;
    delete<T = any>(path: string): Promise<T>;
  }
}

declare module '@nekazari/ui-kit' {
  import type { FC, ReactNode, HTMLAttributes, ButtonHTMLAttributes } from 'react';

  export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
    variant?: 'primary' | 'secondary' | 'ghost' | 'danger';
    size?: 'sm' | 'md' | 'lg';
  }
  export const Button: FC<ButtonProps>;
  export const Card: FC<HTMLAttributes<HTMLDivElement>>;
  export const CardHeader: FC<HTMLAttributes<HTMLDivElement>>;
  export const CardContent: FC<HTMLAttributes<HTMLDivElement>>;
  export const CardTitle: FC<HTMLAttributes<HTMLHeadingElement>>;
  export const Alert: FC<HTMLAttributes<HTMLDivElement> & { variant?: string }>;
}
