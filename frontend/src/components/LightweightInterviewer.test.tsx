import {render,screen} from '@testing-library/react';
import LightweightInterviewer from './LightweightInterviewer';
test('retains original interviewer identity and uses her own mouth asset',()=>{
 vi.stubGlobal('ResizeObserver',class{observe(){}disconnect(){}});
 const {container}=render(<LightweightInterviewer mouthOpeningRef={{current:0}}/>);
 expect(screen.getByAltText('坤曜 AI 面试官')).toHaveAttribute('src','/zoom-interviewer-listening.png');
 expect(container.querySelector('canvas')).toHaveAttribute('width','168');
 expect(container.querySelector('video')).toBeNull();
 vi.unstubAllGlobals();
});
