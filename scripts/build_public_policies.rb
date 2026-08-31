#!/usr/bin/env ruby

require "date"
require "json"
require "yaml"

EXCLUDED_DOCUMENT_TYPES = ["专家共识", "政策观察项"].freeze
ROOT = File.expand_path("..", __dir__)
ENRICHMENT_PATH = File.join(ROOT, "data", "public_enrichment.json")
PUBLIC_FIELDS = %w[policy_id title issuer document_no published_date region policy_category source_url].freeze
REQUIRED_FIELDS = (PUBLIC_FIELDS - ["document_no"]).freeze
CATEGORY_LABELS = {
  "A_十五五与产业支持" => "十五五与产业支持",
  "B_医疗AI应用与卫健治理" => "医疗AI应用与卫健治理",
  "C_医疗器械注册监管" => "医疗器械注册监管",
  "D_医保支付与服务价格" => "医保支付与服务价格",
  "E_医疗数据利用与流通" => "医疗数据利用与流通",
  "F_数据安全与跨境" => "数据安全与跨境",
  "G_地方试点" => "地方政策"
}.freeze

source_dir, output_path = ARGV
abort "usage: build_public_policies.rb MARKDOWN_DIR OUTPUT_JSON" unless source_dir && output_path

def frontmatter(path)
  content = File.read(path, encoding: "UTF-8")
  match = content.match(/\A---\s*\n(.*?)\n---\s*\n/m)
  abort "missing YAML frontmatter: #{path}" unless match
  YAML.safe_load(match[1], permitted_classes: [Date], aliases: false) || {}
end

def public_region(source)
  return source["region"].to_s.strip unless source["policy_category"] == "G_地方试点"

  %w[北京 上海 浙江 深圳 广西 江西].find { |region| source["region"].to_s.include?(region) } || source["region"].to_s.strip
end

def load_enrichment(path)
  payload = JSON.parse(File.read(path, encoding: "UTF-8"))
  entries = payload.fetch("policies")
  entries.each_with_object({}) do |record, memo|
    policy_id = record.fetch("policy_id")
    memo[policy_id] = record
  end
end

enrichment_by_id = load_enrichment(ENRICHMENT_PATH)
records = Dir.glob(File.join(source_dir, "*_原文解析.md")).sort.each_with_object([]) do |path, public_records|
  source = frontmatter(path)
  next if EXCLUDED_DOCUMENT_TYPES.include?(source["document_type"])

  missing = REQUIRED_FIELDS.select { |field| source[field].nil? || source[field].to_s.strip.empty? }
  abort "missing public fields in #{File.basename(path)}: #{missing.join(', ')}" unless missing.empty?
  policy_id = source["policy_id"].to_s.strip
  enrichment = enrichment_by_id[policy_id]
  abort "missing public enrichment for #{policy_id}" unless enrichment

  source_url = enrichment["source_url_override"].to_s.strip
  source_url = source["source_url"].to_s.strip if source_url.empty?
  abort "invalid source URL in #{File.basename(path)}" unless source_url.match?(/\Ahttps?:\/\//)
  quotes = Array(enrichment["important_quotes"]).map { |quote| quote.to_s.strip }.reject(&:empty?)
  abort "missing important quotes for #{policy_id}" if quotes.empty?

  interpretation = enrichment["official_interpretation"].to_s.strip
  abort "missing official interpretation for #{policy_id}" if interpretation.empty?

  record = {
    "policy_id" => policy_id,
    "title" => source["title"].to_s.gsub(/[《》]/, "").strip,
    "issuer" => source["issuer"].to_s.strip,
    "document_no" => source["document_no"].to_s.strip,
    "published_date" => source["published_date"].to_s,
    "region" => public_region(source).empty? ? "全国" : public_region(source),
    "category" => CATEGORY_LABELS.fetch(source["policy_category"]),
    "source_url" => source_url,
    "important_quotes" => quotes,
    "official_interpretation" => interpretation
  }
  interpretation_url = enrichment["official_interpretation_url"].to_s.strip
  record["official_interpretation_url"] = interpretation_url unless interpretation_url.empty?
  public_records << record
end

duplicates = records.group_by { |record| record["source_url"] }.select { |_url, rows| rows.length > 1 }
abort "duplicate public source URLs: #{duplicates.keys.join(', ')}" unless duplicates.empty?

missing_ids = enrichment_by_id.keys - records.map { |record| record["policy_id"] }
abort "unused public enrichment ids: #{missing_ids.join(', ')}" unless missing_ids.empty?

records.sort_by! { |record| [record["published_date"], record["title"]] }.reverse!
payload = {
  "schema_version" => 2,
  "generated_at" => Time.now.getlocal("+08:00").strftime("%Y-%m-%d %H:%M:%S +08:00"),
  "policy_count" => records.length,
  "policies" => records
}

File.write(output_path, JSON.pretty_generate(payload) + "\n", mode: "w", encoding: "UTF-8")
puts "wrote #{records.length} public policy records to #{output_path}"
