import AuthFrame from './auth-frame';
import {Text} from './ui';
export default function AuthConfiguration(){return <AuthFrame title="Sign-in needs setup"><Text role="alert">Sign-in is not configured. Ask the person running Galvanise to connect the approved Clerk development application.</Text></AuthFrame>}
