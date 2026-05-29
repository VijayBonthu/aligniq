// pdfmake's prebuilt bundles ship without (reliable) type declarations and the
// vfs_fonts shape varies across versions. We consume them defensively at the
// call site, so declaring them as `any` modules is sufficient.
declare module 'pdfmake/build/pdfmake';
declare module 'pdfmake/build/vfs_fonts';
