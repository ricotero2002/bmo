This is a [Next.js](https://nextjs.org) project bootstrapped with [`create-next-app`](https://nextjs.org/docs/app/api-reference/cli/create-next-app).

## 🚀 Dependencias y Uso con pnpm

Este proyecto utiliza **pnpm** de forma estricta. Hemos activado medidas de seguridad (`ignore-scripts=true`) para proteger el entorno de desarrollo.

### Reglas Clave:
- **No uses `npm install` ni `yarn`**: Para instalar un paquete nuevo para producción usa `pnpm add <paquete>`. Si es para desarrollo (por ejemplo Jest o Tailwind), usa `pnpm add -D <paquete>`.
- **`pnpm-lock.yaml` es sagrado**: Nunca lo modifiques a mano y asegúrate de commitearlo siempre.
- **Si un paquete falla al instalarse**: Si alguna librería dependía de compilar módulos nativos en la instalación, fallará debido a nuestra seguridad. Si esto ocurre legítimamente, pnpm te informará y podrás correr `pnpm rebuild <paquete>` para darle permiso explícito de forma segura.

### ▶️ Ejecutar el Proyecto (Development)

Para iniciar el servidor de Next.js usa:

```bash
pnpm dev
```

Open [http://localhost:3000](http://localhost:3000) with your browser to see the result.

You can start editing the page by modifying `app/page.tsx`. The page auto-updates as you edit the file.

This project uses [`next/font`](https://nextjs.org/docs/app/building-your-application/optimizing/fonts) to automatically optimize and load [Geist](https://vercel.com/font), a new font family for Vercel.

## Learn More

To learn more about Next.js, take a look at the following resources:

- [Next.js Documentation](https://nextjs.org/docs) - learn about Next.js features and API.
- [Learn Next.js](https://nextjs.org/learn) - an interactive Next.js tutorial.

You can check out [the Next.js GitHub repository](https://github.com/vercel/next.js) - your feedback and contributions are welcome!

## Deploy on Vercel

The easiest way to deploy your Next.js app is to use the [Vercel Platform](https://vercel.com/new?utm_medium=default-template&filter=next.js&utm_source=create-next-app&utm_campaign=create-next-app-readme) from the creators of Next.js.

Check out our [Next.js deployment documentation](https://nextjs.org/docs/app/building-your-application/deploying) for more details.
