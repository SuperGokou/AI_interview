import '@testing-library/jest-dom';

// ── jsdom polyfills required by Avatar3D & Three.js ──────────────────────────

// 1. window.matchMedia (used for prefers-reduced-motion detection)
if (typeof window.matchMedia === 'undefined') {
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    value: (query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: () => {},
      removeListener: () => {},
      addEventListener: () => {},
      removeEventListener: () => {},
      dispatchEvent: () => false,
    }),
  });
}

// 2. HTMLCanvasElement.getContext — jsdom doesn't support WebGL; return a
//    minimal stub so Three.js WebGLRenderer can be instantiated without
//    throwing. The canvas mock must also implement getExtension / getParameter
//    because Three.js probes them during construction.
const originalGetContext = HTMLCanvasElement.prototype.getContext;
HTMLCanvasElement.prototype.getContext = function (
  contextId: string,
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  ...rest: any[]
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
): any {
  if (contextId === 'webgl' || contextId === 'webgl2') {
    return {
      canvas: this,
      drawingBufferWidth: 300,
      drawingBufferHeight: 150,
      getExtension: () => null,
      getParameter: () => null,
      getShaderPrecisionFormat: () => ({ rangeMin: 127, rangeMax: 127, precision: 23 }),
      enable: () => {},
      disable: () => {},
      clearColor: () => {},
      clearDepth: () => {},
      clearStencil: () => {},
      depthFunc: () => {},
      depthMask: () => {},
      blendEquation: () => {},
      blendEquationSeparate: () => {},
      blendFunc: () => {},
      blendFuncSeparate: () => {},
      colorMask: () => {},
      stencilMask: () => {},
      stencilFunc: () => {},
      stencilOp: () => {},
      pixelStorei: () => {},
      viewport: () => {},
      scissor: () => {},
      bindFramebuffer: () => {},
      bindTexture: () => {},
      activeTexture: () => {},
      texParameteri: () => {},
      texImage2D: () => {},
      createShader: () => ({}),
      shaderSource: () => {},
      compileShader: () => {},
      getShaderParameter: () => true,
      createProgram: () => ({}),
      attachShader: () => {},
      linkProgram: () => {},
      getProgramParameter: () => true,
      useProgram: () => {},
      createBuffer: () => ({}),
      bindBuffer: () => {},
      bufferData: () => {},
      createVertexArray: () => ({}),
      bindVertexArray: () => {},
      createTexture: () => ({}),
      deleteTexture: () => {},
      deleteBuffer: () => {},
      deleteProgram: () => {},
      deleteShader: () => {},
      deleteVertexArray: () => {},
      deleteFramebuffer: () => {},
      createRenderbuffer: () => ({}),
      bindRenderbuffer: () => {},
      renderbufferStorage: () => {},
      framebufferTexture2D: () => {},
      framebufferRenderbuffer: () => {},
      createFramebuffer: () => ({}),
      checkFramebufferStatus: () => 36053, // FRAMEBUFFER_COMPLETE
      generateMipmap: () => {},
      getUniformLocation: () => ({}),
      getAttribLocation: () => 0,
      enableVertexAttribArray: () => {},
      vertexAttribPointer: () => {},
      uniform1i: () => {},
      uniform1f: () => {},
      uniform2f: () => {},
      uniform3f: () => {},
      uniform4f: () => {},
      uniform1fv: () => {},
      uniform2fv: () => {},
      uniform3fv: () => {},
      uniform4fv: () => {},
      uniformMatrix3fv: () => {},
      uniformMatrix4fv: () => {},
      drawArrays: () => {},
      drawElements: () => {},
      clear: () => {},
      flush: () => {},
      finish: () => {},
      getError: () => 0,
      readPixels: () => {},
      isContextLost: () => false,
    };
  }
  // Fall through to real implementation for 2d, bitmaprenderer, etc.
  // eslint-disable-next-line @typescript-eslint/no-unsafe-return
  return originalGetContext.call(this, contextId as '2d', ...rest);
};

// 3. requestAnimationFrame / cancelAnimationFrame — already present in jsdom
//    but just ensure they exist with no-op fallbacks if somehow absent.
if (typeof globalThis.requestAnimationFrame === 'undefined') {
  globalThis.requestAnimationFrame = (cb) => setTimeout(cb, 16) as unknown as number;
  globalThis.cancelAnimationFrame = (id) => clearTimeout(id);
}
