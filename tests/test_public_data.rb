#!/usr/bin/env ruby

require "json"
require "minitest/autorun"

ROOT = File.expand_path("..", __dir__)
DATA = JSON.parse(File.read(File.join(ROOT, "data", "policies.json"), encoding: "UTF-8"))

class PublicDataTest < Minitest::Test
  ALLOWED_FIELDS = %w[title issuer document_no published_date region category source_url].sort.freeze
  FORBIDDEN_TEXT = ["德适", "建议行动", "责任部门", "内部假设", "/Users/", "local_source", "研判"].freeze

  def test_payload_count_is_consistent
    assert_equal DATA.fetch("policy_count"), DATA.fetch("policies").length
  end

  def test_only_whitelisted_fields_are_public
    DATA.fetch("policies").each do |record|
      assert_equal ALLOWED_FIELDS, record.keys.sort
      assert_match(%r{\Ahttps?://}, record.fetch("source_url"))
    end
  end

  def test_internal_language_and_paths_are_absent
    serialized = JSON.generate(DATA)
    FORBIDDEN_TEXT.each { |term| refute_includes serialized, term }
  end

  def test_no_duplicate_source_urls
    urls = DATA.fetch("policies").map { |record| record.fetch("source_url") }
    assert_equal urls.uniq.length, urls.length
  end
end
