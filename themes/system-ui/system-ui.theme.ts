// The system-ui theme. `astryx experimental theme editor` wrote this file once and never changes it again.
// The checked settings live in system-ui.settings.json and the generated system-ui.settings.ts;
// change them with `astryx experimental theme editor set system-ui ...`. Add your own changes below: they win over the settings.
import {defineTheme} from '@astryxdesign/core/theme';
import {systemUiSettings} from './system-ui.settings';

export const systemUiTheme = defineTheme({
  extends: systemUiSettings,
  name: 'system-ui',
});
