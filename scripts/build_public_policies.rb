#!/usr/bin/env ruby

require "date"
require "json"
require "yaml"

EXCLUDED_DOCUMENT_TYPES = ["专家共识", "政策观察项"].freeze
PUBLIC_FIELDS = %w[title issuer document_no published_date region policy_category source_url].freeze
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
  return "全国" unless source["policy_category"] == "G_地方试点"

  %w[北京 上海 浙江 深圳 广西 江西].find { |region| source["region"].to_s.include?(region) } || source["region"].to_s.strip
end

records = Dir.glob(File.join(source_dir, "*_原文解析.md")).sort.each_with_object([]) do |path, public_records|
  source = frontmatter(path)
  next if EXCLUDED_DOCUMENT_TYPES.include?(source["document_type"])

  missing = REQUIRED_FIELDS.select { |field| source[field].nil? || source[field].to_s.strip.empty? }
  abort "missing public fields in #{File.basename(path)}: #{missing.join(', ')}" unless missing.empty?
  abort "invalid source URL in #{File.basename(path)}" unless source["source_url"].match?(/\Ahttps?:\/\//)

  public_records << {
    "title" => source["title"].to_s.gsub(/[《》]/, "").strip,
    "issuer" => source["issuer"].to_s.strip,
    "document_no" => source["document_no"].to_s.strip,
    "published_date" => source["published_date"].to_s,
    "region" => public_region(source),
    "category" => CATEGORY_LABELS.fetch(source["policy_category"]),
    "source_url" => source["source_url"].to_s.strip
  }
end

duplicates = records.group_by { |record| record["source_url"] }.select { |_url, rows| rows.length > 1 }
abort "duplicate public source URLs: #{duplicates.keys.join(', ')}" unless duplicates.empty?

records.sort_by! { |record| [record["published_date"], record["title"]] }.reverse!
payload = {
  "schema_version" => 1,
  "generated_at" => Time.now.getlocal("+08:00").strftime("%Y-%m-%d %H:%M:%S +08:00"),
  "policy_count" => records.length,
  "policies" => records
}

File.write(output_path, JSON.pretty_generate(payload) + "\n", mode: "w", encoding: "UTF-8")
puts "wrote #{records.length} public policy records to #{output_path}"
