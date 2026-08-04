export type AffiliateCommentTemplate = {
  id: string;
  workspace_id: string;
  platform: "FACEBOOK_REELS";
  name: string;
  message_template: string;
  default_cta: string;
  default_disclosure: string;
  attach_product_image: boolean;
  version: number;
  is_active: boolean;
  metadata_json: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
};

export type AffiliateCommentTemplateInput = {
  platform?: "FACEBOOK_REELS";
  name: string;
  message_template: string;
  default_cta: string;
  default_disclosure: string;
  attach_product_image: boolean;
};

export type AffiliateCommentTemplateListResponse = {
  templates: AffiliateCommentTemplate[];
  active_template_id: string | null;
};
