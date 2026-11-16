export interface OccasionShortcut {
  /** Short chip label. */
  label: string;
  /** Full request sent to the stylist. */
  prompt: string;
}

export const OCCASION_SHORTCUTS: OccasionShortcut[] = [
  {
    label: 'Cafe ở Đà Lạt',
    prompt: 'Đi cafe ngoài trời ở Đà Lạt, se lạnh, muốn set đồ lịch sự nhẹ nhàng',
  },
  {
    label: 'Đi làm ngày hè',
    prompt: 'Đi làm văn phòng ngày hè ở Hà Nội, ưu tiên thoải mái thoáng mát',
  },
  {
    label: 'Tiệc sinh nhật tối',
    prompt: 'Dự tiệc sinh nhật bạn thân buổi tối ở TP. Hồ Chí Minh, phong cách smart casual',
  },
  {
    label: 'Dạo phố cuối tuần',
    prompt: 'Dạo phố cuối tuần, thời tiết mát mẻ, phong cách tối giản',
  },
];

/** Query-string key used to hand a request from the home page to the stylist page. */
export const STYLIST_QUERY_PARAM = 'q';
