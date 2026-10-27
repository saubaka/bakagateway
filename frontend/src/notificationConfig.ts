// Local notification display defaults; no external service dependency.
import { copyUiConfigV2, defaultUiConfigV2 } from './shared/notificationDisplay.ts';
const current = defaultUiConfigV2();
export const snapshotUiConfigV2 = () => copyUiConfigV2(current);
