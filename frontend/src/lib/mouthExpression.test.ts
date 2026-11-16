import {mouthExpression,smoothMouth} from './mouthExpression';
test('silence restores the original closed mouth',()=>{
 expect(mouthExpression(0).visible).toBe(false);
 expect(mouthExpression(NaN).visible).toBe(false);
});
test('single mouth keeps its width and only opens slightly',()=>{
 const soft=mouthExpression(.08),strong=mouthExpression(.7);
 expect(soft.visible).toBe(true);expect(strong.height).toBeGreaterThan(soft.height);
 expect(strong.width).toBe(soft.width);
 expect(strong.height).toBeLessThanOrEqual(.58);
 expect(strong.jawDrop).toBeLessThanOrEqual(1.5);
 expect(strong.jawDrop).toBeGreaterThan(soft.jawDrop);
 expect(strong.opacity).toBe(1);expect(soft.opacity).toBeGreaterThan(0);
});
test('extreme audio cannot distort the face beyond bounded motion',()=>{
 expect(mouthExpression(100)).toEqual(mouthExpression(.9));
 expect(mouthExpression(-1).visible).toBe(false);
});
test('low-energy boundary does not pop from hidden to opaque',()=>{
 const below=mouthExpression(.017),above=mouthExpression(.019);
 expect(mouthExpression(0).opacity).toBe(0);
 expect(Math.abs(above.opacity-below.opacity)).toBeLessThan(.03);
 expect(above.opacity).toBeLessThan(.05);
});

test('animation eases through a brief gap and settles after silence',()=>{
 const open=smoothMouth(0,.9,1/60);expect(open).toBeLessThan(.25);
 const gap=smoothMouth(.5,0,1/60);expect(gap).toBeGreaterThan(.4);
 let value=.5;for(let n=0;n<60;n++)value=smoothMouth(value,0,1/60);
 expect(value).toBeLessThan(.001);
});
