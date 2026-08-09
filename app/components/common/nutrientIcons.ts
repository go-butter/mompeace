import type { FC } from 'react';
import type { SvgProps } from 'react-native-svg';

import CaffeineIcon from '@/assets/images/foodDiary/caffeine.svg';
import CaloriesIcon from '@/assets/images/foodDiary/calories.svg';
import CarbohydrateIcon from '@/assets/images/foodDiary/carbohydrate.svg';
import FatIcon from '@/assets/images/foodDiary/fat.svg';
import IronIcon from '@/assets/images/foodDiary/iron.svg';
import ProteinIcon from '@/assets/images/foodDiary/protein.svg';
import SodiumIcon from '@/assets/images/foodDiary/sodium.svg';
import SugarIcon from '@/assets/images/foodDiary/sugar.svg';
import { SelectableNutrientKey } from '@/constants/nutrients';

/** 선택 가능한 7개 + 카페인. 카페인은 선택 대상이 아니지만 아이콘이 필요한 화면
 *  (리포트)이 있어 여기에 함께 둔다. */
export type NutrientIconKey = SelectableNutrientKey | 'caffeine';

// 컴포넌트를 그대로 담는다(<Icon />로 미리 만들어 두지 않는다) — 호출부마다 크기와
// 색이 다르기 때문이다. 리포트는 상태색으로, OCR 확인 화면은 분홍으로 칠한다.
// 8개 SVG 모두 currentColor를 쓰므로 color prop이 그대로 먹는다.
export const NUTRIENT_ICONS: Record<NutrientIconKey, FC<SvgProps>> = {
  caffeine: CaffeineIcon,
  carbohydrate: CarbohydrateIcon,
  sugar: SugarIcon,
  // 에너지 아이콘의 파일명은 energy가 아니라 calories다.
  energy: CaloriesIcon,
  fat: FatIcon,
  iron: IronIcon,
  protein: ProteinIcon,
  sodium: SodiumIcon,
};
