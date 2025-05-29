import { Html, Head, Main, NextScript } from 'next/document'

export default function Document() {
  return (
    <Html lang="en">
      <Head>
        <meta name="description" content="Real-time NYC Subway anomaly detection and monitoring" />
        <link rel="icon" href="/favicon.ico" />
        <link href='https://api.mapbox.com/mapbox-gl-js/v3.9.0/mapbox-gl.css' rel='stylesheet' />
      </Head>
      <body className="bg-gray-950 text-gray-100">
        <Main />
        <NextScript />
      </body>
    </Html>
  )
}