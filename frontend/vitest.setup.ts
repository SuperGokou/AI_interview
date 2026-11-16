import '@testing-library/jest-dom';

// jsdom polyfills required by canvas-based avatar rendering.

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
      checkFramebufferStatus: () => 36053,
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

  if (contextId === '2d') {
    return {
      canvas: this,
      clearRect: () => {},
      drawImage: () => {},
      getImageData: (_x: number, _y: number, width: number, height: number) => ({
        data: new Uint8ClampedArray(Math.max(1, width * height * 4)).fill(128),
      }),
      putImageData: () => {},
    };
  }

  // eslint-disable-next-line @typescript-eslint/no-unsafe-return
  return originalGetContext.call(this, contextId as '2d', ...rest);
};

if (typeof globalThis.requestAnimationFrame === 'undefined') {
  globalThis.requestAnimationFrame = (cb) => setTimeout(cb, 16) as unknown as number;
  globalThis.cancelAnimationFrame = (id) => clearTimeout(id);
}
